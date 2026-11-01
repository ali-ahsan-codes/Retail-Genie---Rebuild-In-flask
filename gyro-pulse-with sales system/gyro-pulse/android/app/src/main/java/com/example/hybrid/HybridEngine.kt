package com.example.hybrid

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URI
import java.net.URL
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec
import java.security.KeyFactory
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.KeyGenerator
import javax.crypto.Mac
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.HttpsURLConnection

/** Connected-mode pilot. No legacy preferences, device keys, workers, GPC or master secret. */
class HybridEngine(context: Context, namespace: String = "v1") {
    private val checkedNamespace = namespace.also { check(it.matches(Regex("[a-z0-9-]{1,64}"))) }
    private val aesAlias = "retail.hybrid.aes.$checkedNamespace"
    private val signAlias = "retail.hybrid.sign.$checkedNamespace"
    private val file = AtomicFile(java.io.File(context.noBackupFilesDir, "hybrid-state.$checkedNamespace"))
    private val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    private val aad = (context.packageName + ":hybrid-state.$checkedNamespace").toByteArray(Charsets.UTF_8)
    private val random = SecureRandom()
    private val label = "retail.hybrid.office-envelope.v1".toByteArray(Charsets.UTF_8)

    init { synchronized(lock) {
        // Key loss never silently recreates keys over an existing queue.
        if (!keys.containsAlias(signAlias)) {
            check(!hasData()) { "Signing key lost; retain data for operator recovery" }
            KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply {
                initialize(KeyGenParameterSpec.Builder(signAlias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256).build())
            }.generateKeyPair()
        }
        if (!keys.containsAlias(aesAlias)) {
            check(!hasData()) { "Encryption key lost; no plaintext fallback" }
            KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
                init(KeyGenParameterSpec.Builder(aesAlias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256).build())
            }.generateKey()
        }
        val state = read()
        if (!state.has("device_id")) { state.put("device_id", UUID.randomUUID().toString()); write(state) }
    } }

    private fun encode(raw: ByteArray): String = Base64.encodeToString(raw, Base64.NO_WRAP)
    private fun decode(raw: String): ByteArray = Base64.decode(raw, Base64.NO_WRAP)
    private fun sha(raw: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(raw).joinToString("") { "%02x".format(it.toInt() and 255) }
    fun deviceId(): String = synchronized(lock) { read().getString("device_id") }
    fun publicKey(): String = encode(keys.getCertificate(signAlias).publicKey.encoded)
    fun fingerprint(): String = sha(keys.getCertificate(signAlias).publicKey.encoded)

    private fun hasData(): Boolean = listOf(file.baseFile, java.io.File(file.baseFile.path + ".bak"), java.io.File(file.baseFile.path + ".new")).any { it.exists() }
    private fun read(): JSONObject {
        if (!hasData()) return JSONObject()
        val output = ByteArrayOutputStream()
        file.openRead().use { input ->
            val buffer = ByteArray(4096)
            while (true) { val count = input.read(buffer); if (count < 0) break; check(output.size() + count <= 2097152); output.write(buffer, 0, count) }
        }
        val bytes = output.toByteArray(); check(bytes.size >= 29)
        check(bytes[0] == 1.toByte())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, keys.getKey(aesAlias, null) as SecretKey, GCMParameterSpec(128, bytes.copyOfRange(1, 13)))
        cipher.updateAAD(aad)
        return JSONObject(String(cipher.doFinal(bytes.copyOfRange(13, bytes.size)), Charsets.UTF_8))
    }
    private fun write(state: JSONObject) {
        val raw = state.toString().toByteArray(Charsets.UTF_8)
        check(raw.size <= 2000000) { "Encrypted queue capacity reached; do not discard unsent data" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, keys.getKey(aesAlias, null) as SecretKey)
        cipher.updateAAD(aad)
        val encrypted = byteArrayOf(1) + cipher.iv + cipher.doFinal(raw)
        val output = file.startWrite()
        try { output.write(encrypted); file.finishWrite(output) }
        catch (error: Exception) { file.failWrite(output); throw error }
    }
    private fun origin(value: String): String {
        check(value.length <= 300 && value.none { it <= ' ' } && !value.contains('?') && !value.contains('#'))
        val uri = URI(value)
        check(uri.scheme == "https" && !uri.host.isNullOrEmpty() && uri.rawUserInfo == null && (uri.path.isNullOrEmpty() || uri.path == "/") && (uri.port == -1 || uri.port in 1..65535))
        return value.trimEnd('/')
    }
    private fun uuid(value: String) { check(UUID.fromString(value).toString() == value && value != "00000000-0000-0000-0000-000000000000") }
    private fun http(base: String, path: String, body: JSONObject? = null, profile: JSONObject? = null): JSONObject {
        val allowed = setOf("/api/v1/devices/enroll", "/api/v1/device/orders", "/api/v1/field-device/orders")
        check(path in allowed || path.matches(Regex("/api/v1/device/catalog/[A-Za-z0-9_-]{1,64}")))
        check(path != "/api/v1/field-device/orders" || profile == null) // NEVER cloud bearer on LAN
        val connection = URL(origin(base) + path).openConnection(java.net.Proxy.NO_PROXY) as HttpsURLConnection
        connection.instanceFollowRedirects = false
        connection.connectTimeout = 10000; connection.readTimeout = 10000
        connection.requestMethod = if (body == null) "GET" else "POST"
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("Content-Type", "application/json")
        if (profile != null) {
            check(origin(profile.getString("base_url")) == origin(base))
            val token = profile.getString("access_token"); check(token.matches(Regex("[A-Za-z0-9_-]{43}")))
            connection.setRequestProperty("Authorization", "Bearer $token")
            for ((header, field) in listOf("X-Company-ID" to "company_id", "X-Instance-ID" to "instance_id", "X-Office-ID" to "office_id", "X-Device-ID" to "device_id")) connection.setRequestProperty(header, profile.getString(field))
        }
        try {
            if (body != null) { val raw = body.toString().toByteArray(Charsets.UTF_8); check(raw.size <= 65536); connection.doOutput = true; connection.outputStream.use { it.write(raw) } }
            check(connection.responseCode == 200) { "Cloud/office rejected request; keep immutable queue" }
            check(connection.contentType?.substringBefore(';') == "application/json")
            val output = ByteArrayOutputStream()
            connection.inputStream.use { input ->
                val buffer = ByteArray(4096)
                while (true) { val count = input.read(buffer); if (count < 0) break; check(output.size() + count <= 132096); output.write(buffer, 0, count) }
            }
            return JSONObject(String(output.toByteArray(), Charsets.UTF_8))
        } finally { connection.disconnect() }
    }
    fun enroll(trustedOrigin: String, grantText: String) = synchronized(lock) {
        check(grantText.toByteArray().size <= 16384)
        val grant = JSONObject(grantText)
        check(origin(grant.getString("base_url")) == origin(trustedOrigin))
        check(grant.getString("device_id") == deviceId() && grant.getString("key_fingerprint") == fingerprint())
        for (field in listOf("company_id", "instance_id", "office_id", "device_id")) uuid(grant.getString(field))
        val state = read()
        if (state.has("profile")) for (field in listOf("company_id", "instance_id", "office_id", "device_id", "base_url")) check(state.getJSONObject("profile").getString(field) == grant.getString(field))
        val challenge = ("retail.hybrid.device.enroll.v1|" + grant.getString("grant_id") + "|" + grant.getString("pairing_code")).toByteArray(Charsets.US_ASCII)
        val proof = Signature.getInstance("SHA256withECDSA").apply { initSign(keys.getKey(signAlias, null) as java.security.PrivateKey); update(challenge) }.sign()
        val response = http(trustedOrigin, "/api/v1/devices/enroll", JSONObject().put("grant", grant).put("public_key", publicKey()).put("proof", encode(proof)))
        check(response.getInt("schema_version") == 1 && response.getString("key_fingerprint") == fingerprint())
        for (field in listOf("company_id", "instance_id", "office_id", "device_id", "base_url")) check(response.getString(field) == grant.getString(field))
        check(response.getString("access_token").matches(Regex("[A-Za-z0-9_-]{43}")))
        check(response.getJSONArray("scopes").toString() == JSONArray(listOf("catalog:read", "orders:submit")).toString())
        state.put("profile", response); write(state)
    }
    fun downloadCatalog(storeId: String): String = synchronized(lock) {
        check(storeId.matches(Regex("[A-Za-z0-9_-]{1,64}")))
        val state = read(); val profile = state.getJSONObject("profile")
        val snapshot = http(profile.getString("base_url"), "/api/v1/device/catalog/$storeId", profile = profile)
        check(snapshot.getBoolean("read_only") && snapshot.getString("inventory_authority") == "retail-genie")
        val payload = snapshot.getJSONObject("payload"); check(payload.getString("mode") == "full" && payload.getJSONObject("store").getString("id") == storeId)
        val catalogs = state.optJSONObject("catalogs") ?: JSONObject()
        if (catalogs.has(storeId)) check(payload.getLong("sequence") >= catalogs.getJSONObject(storeId).getJSONObject("payload").getLong("sequence"))
        catalogs.put(storeId, snapshot); state.put("catalogs", catalogs); write(state)
        return "Read-only catalog cached: ${payload.getJSONArray("items").length()} products. On-hand is not a reservation."
    }
    fun proposalTemplate(storeId: String): String = synchronized(lock) {
        val snapshot = read().getJSONObject("catalogs").getJSONObject(storeId)
        val products = snapshot.getJSONObject("payload").getJSONArray("items")
        val lines = JSONArray()
        for (index in 0 until products.length()) {
            val product = products.getJSONObject(index)
            if (product.getBoolean("active") && !product.isNull("price")) { lines.put(JSONObject().put("product_id", product.getString("id")).put("quantity", 1).put("unit_price", product.getString("price"))); break }
        }
        check(lines.length() == 1)
        JSONObject().put("schema_version", 1).put("order_id", UUID.randomUUID().toString()).put("store_id", storeId)
            .put("catalog_message_id", snapshot.getString("message_id")).put("customer_phone", "")
            .put("customer_name", JSONObject.NULL).put("items", lines).toString(2)
    }
    fun queue(proposal: String): String = synchronized(lock) {
        check(proposal.toByteArray(Charsets.UTF_8).size <= 14000)
        val order = JSONObject(proposal); validateOrder(order)
        val state = read(); val profile = state.getJSONObject("profile")
        val pending = state.optJSONObject("orders") ?: JSONObject()
        val id = order.getString("order_id"); val hash = sha(canonical(order).toByteArray(Charsets.UTF_8))
        if (pending.has(id)) { check(pending.getJSONObject(id).getString("hash") == hash); return@synchronized id }
        check(pending.length() < 100) { "Queue full; no automatic deletion" }
        val body = JSONObject().put("schema_version", 1).put("order", order)
        for (field in listOf("company_id", "instance_id", "office_id", "device_id")) body.put(field, profile.getString(field))
        val raw = body.toString().toByteArray(Charsets.UTF_8); check(raw.size <= 16384)
        val signature = Signature.getInstance("SHA256withECDSA").apply { initSign(keys.getKey(signAlias, null) as java.security.PrivateKey); update(raw) }.sign()
        val wire = JSONObject().put("body", encode(raw)).put("signature", encode(signature))
        pending.put(id, JSONObject().put("wire", wire).put("hash", hash).put("state", "pending"))
        state.put("orders", pending); write(state); id
    }
    fun syncCloud(): String = synchronized(lock) {
        val state = read(); val profile = state.getJSONObject("profile"); val orders = state.optJSONObject("orders") ?: JSONObject()
        var count = 0
        for (id in orders.keys().asSequence().toList()) {
            val entry = orders.getJSONObject(id)
            if (entry.getString("state") == "cloud_received") continue
            val result = http(profile.getString("base_url"), "/api/v1/device/orders", entry.getJSONObject("wire"), profile)
            check(result.getInt("schema_version") == 1 && result.getString("order_id") == id && result.getString("payload_sha256") == entry.getString("hash") && result.getString("status") == "cloud_received")
            entry.put("state", "cloud_received"); state.put("orders", orders); write(state); count++
        }
        "$count cloud receipts verified; all orders retained. Native approval status is unknown."
    }
    fun officeParcel(orderId: String): String = synchronized(lock) {
        val state = read(); val profile = state.getJSONObject("profile")
        check(!profile.isNull("office_public_key")) { "Office recipient key not configured; no plaintext export" }
        val peer = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(decode(profile.getString("office_public_key"))))
        val ephemeral = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val shared = KeyAgreement.getInstance("ECDH").apply { init(ephemeral.private); doPhase(peer, true) }.generateSecret()
        // RFC 5869 HKDF-SHA256, salt=None => 32 zero bytes, single expansion block.
        val hmac = Mac.getInstance("HmacSHA256"); hmac.init(SecretKeySpec(ByteArray(32), "HmacSHA256")); val prk = hmac.doFinal(shared)
        hmac.init(SecretKeySpec(prk, "HmacSHA256")); val key = hmac.doFinal(label + byteArrayOf(1))
        val nonce = ByteArray(12).also { random.nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce))
        val identity = listOf("company_id", "instance_id", "office_id").map { profile.getString(it) }
        cipher.updateAAD((String(label, Charsets.UTF_8) + "|" + identity.joinToString("|")).toByteArray(Charsets.UTF_8))
        val wire = state.getJSONObject("orders").getJSONObject(orderId).getJSONObject("wire").toString().toByteArray(Charsets.UTF_8)
        val parcel = JSONObject().put("schema_version", 1).put("ephemeral_key", encode(ephemeral.public.encoded)).put("nonce", encode(nonce)).put("ciphertext", encode(cipher.doFinal(wire)))
        for (field in listOf("company_id", "instance_id", "office_id")) parcel.put(field, profile.getString(field))
        parcel.toString()
    }
    fun sendLan(orderId: String): String = synchronized(lock) {
        val profile = read().getJSONObject("profile")
        check(!profile.isNull("office_origin")) { "No explicitly enrolled office HTTPS origin" }
        http(profile.getString("office_origin"), "/api/v1/field-device/orders", JSONObject(officeParcel(orderId)), null)
        // An unsigned LAN response must NEVER erase/ack a device order.
        "Office response is unconfirmed; order retained for cloud reconciliation and human review."
    }
    fun summary(): String = synchronized(lock) {
        val state = read(); val orders = state.optJSONObject("orders") ?: JSONObject()
        "Device: ${state.getString("device_id")}\nSigning fingerprint: ${fingerprint()}\nEnrolled: ${state.has("profile")}\nRetained orders: ${orders.length()}"
    }
    private fun validateOrder(order: JSONObject) {
        check(order.keys().asSequence().toSet() == setOf("schema_version", "order_id", "store_id", "catalog_message_id", "customer_phone", "customer_name", "items"))
        check(order.get("schema_version") == 1); uuid(order.getString("order_id")); uuid(order.getString("catalog_message_id"))
        check(order.getString("store_id").length in 1..64)
        val phone = order.getString("customer_phone"); check(phone.length <= 64 && phone.matches(Regex("[+0-9 ()-]+")) && phone.count { it in '0'..'9' } in 7..15)
        if (!order.isNull("customer_name")) check(order.getString("customer_name").length in 1..160)
        val lines = order.getJSONArray("items"); check(lines.length() in 1..50)
        val ids = mutableSetOf<String>()
        for (index in 0 until lines.length()) {
            val line = lines.getJSONObject(index)
            check(line.keys().asSequence().toSet() == setOf("product_id", "quantity", "unit_price"))
            check(line.getString("product_id").length in 1..64 && ids.add(line.getString("product_id")))
            check(line.get("quantity") is Int && line.getInt("quantity") in 1..10000)
            check(line.getString("unit_price").matches(Regex("(?:0|[1-9][0-9]{0,10})\\.[0-9]{3}")) && java.math.BigDecimal(line.getString("unit_price")) > java.math.BigDecimal.ZERO)
        }
    }
    private fun quote(value: String): String = buildString {
        append('"')
        for (ch in value) when (ch) {
            '"' -> append("\\\""); '\\' -> append("\\\\"); '\b' -> append("\\b"); '\u000c' -> append("\\f"); '\n' -> append("\\n"); '\r' -> append("\\r"); '\t' -> append("\\t")
            else -> if (ch < ' ') append("\\u%04x".format(ch.code)) else append(ch)
        }
        append('"')
    }
    private fun canonical(value: Any?): String = when(value) {
        null, JSONObject.NULL -> "null"
        is String -> quote(value)
        is JSONObject -> value.keys().asSequence().toList().sorted().joinToString(",", "{", "}") { quote(it) + ":" + canonical(value.get(it)) }
        is JSONArray -> (0 until value.length()).joinToString(",", "[", "]") { canonical(value.get(it)) }
        is Int, is Long, is Boolean -> value.toString()
        else -> error("Unsupported JSON value")
    }
    companion object { private val lock = Any() }
}
