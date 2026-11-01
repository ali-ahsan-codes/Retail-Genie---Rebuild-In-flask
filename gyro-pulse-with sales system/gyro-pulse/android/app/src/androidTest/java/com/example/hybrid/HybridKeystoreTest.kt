package com.example.hybrid

import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID
import org.json.JSONObject
import org.json.JSONArray

/** Must execute on emulator AND physical device; source presence is not a test pass.
 * Random namespace: never delete/replace a real user's keys or retained queue.
 */
@RunWith(AndroidJUnit4::class)
class HybridKeystoreTest {
    @Test fun encryptedIdentitySurvivesRecreation() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext.also { assertEquals("com.retailgenie.hybrid.pilot.debug", it.packageName) }
        val namespace = "test-" + UUID.randomUUID().toString()
        val first = HybridEngine(context, namespace)
        val file = File(context.noBackupFilesDir, "hybrid-state.$namespace")
        assertTrue(file.exists())
        assertFalse(String(file.readBytes(), Charsets.ISO_8859_1).contains(first.deviceId()))
        assertEquals(first.deviceId(), HybridEngine(context, namespace).deviceId())
        assertEquals(first.fingerprint(), HybridEngine(context, namespace).fingerprint())
    }
    @Test fun modifiedCiphertextFailsClosed() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext.also { assertEquals("com.retailgenie.hybrid.pilot.debug", it.packageName) }
        val namespace = "test-" + UUID.randomUUID().toString()
        HybridEngine(context, namespace)
        val file = File(context.noBackupFilesDir, "hybrid-state.$namespace")
        val bytes = file.readBytes(); bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte(); file.writeBytes(bytes)
        var rejected = false
        try { HybridEngine(context, namespace) } catch (expected: Exception) { rejected = true }
        assertTrue(rejected)
    }
    @Test fun immutableQueueEncryptedAcrossRestart() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext.also { assertEquals("com.retailgenie.hybrid.pilot.debug", it.packageName) }
        val namespace = "test-" + UUID.randomUUID().toString()
        val engine = HybridEngine(context, namespace)
        // Private test setup only, no production provisioning or network/TLS bypass.
        val reader = HybridEngine::class.java.getDeclaredMethod("read").apply { isAccessible = true }
        val writer = HybridEngine::class.java.getDeclaredMethod("write", JSONObject::class.java).apply { isAccessible = true }
        val profile = JSONObject().put("company_id", UUID.randomUUID().toString()).put("instance_id", UUID.randomUUID().toString()).put("office_id", UUID.randomUUID().toString()).put("device_id", engine.deviceId())
        val state = reader.invoke(engine) as JSONObject; state.put("profile", profile); writer.invoke(engine, state)
        val order = JSONObject().put("schema_version", 1).put("order_id", UUID.randomUUID().toString()).put("catalog_message_id", UUID.randomUUID().toString()).put("store_id", "store-1").put("customer_name", "private-device-test-marker").put("customer_phone", "+96800000000").put("items", JSONArray().put(JSONObject().put("product_id", "product-1").put("quantity", 1).put("unit_price", "1.250")))
        val id = engine.queue(order.toString()); assertEquals(id, engine.queue(order.toString()))
        assertFalse(String(File(context.noBackupFilesDir, "hybrid-state.$namespace").readBytes(), Charsets.ISO_8859_1).contains("private-device-test-marker"))
        val restarted = HybridEngine(context, namespace)
        assertEquals(id, restarted.queue(order.toString()))
        order.getJSONArray("items").getJSONObject(0).put("quantity", 2)
        var rejected = false
        try { restarted.queue(order.toString()) } catch (expected: Exception) { rejected = true }
        assertTrue(rejected)
    }
    @Test fun canonicalHashMatchesPythonUnicodeVector() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext.also { assertEquals("com.retailgenie.hybrid.pilot.debug", it.packageName) }
        val engine = HybridEngine(context, "test-" + UUID.randomUUID().toString())
        val value = JSONObject().put("name", "متجر / <p> \u2028 😀").put("amount", "1.250")
            .put("null", JSONObject.NULL).put("qty", 2)
            .put("items", JSONArray().put(true).put("a\\b\"c"))
        val method = HybridEngine::class.java.getDeclaredMethod("canonical", Any::class.java).apply { isAccessible = true }
        val canonical = method.invoke(engine, value) as String
        val digest = java.security.MessageDigest.getInstance("SHA-256").digest(canonical.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it.toInt() and 255) }
        // Generated independently using Python json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":")).
        assertEquals("33fce1f3de37d77f41af215cb10aba999689c2ad58a9886131e572d8e3996a34", digest)
    }

    @Test fun archiveOnlyTerminalAfterVerifiedExportKeepsPending() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext.also { assertEquals("com.retailgenie.hybrid.pilot.debug", it.packageName) }
        val engine = HybridEngine(context, "test-" + UUID.randomUUID().toString())
        val reader = HybridEngine::class.java.getDeclaredMethod("read").apply { isAccessible = true }
        val writer = HybridEngine::class.java.getDeclaredMethod("write", JSONObject::class.java).apply { isAccessible = true }
        val state = reader.invoke(engine) as JSONObject
        val profile = JSONObject().put("company_id", UUID.randomUUID().toString()).put("instance_id", UUID.randomUUID().toString()).put("office_id", UUID.randomUUID().toString()).put("device_id", engine.deviceId()).put("access_token", "never-archive-credential-marker")
        state.put("profile", profile); writer.invoke(engine, state)
        val order = JSONObject().put("schema_version", 1).put("order_id", UUID.randomUUID().toString()).put("catalog_message_id", UUID.randomUUID().toString()).put("store_id", "store-1").put("customer_name", "archive-private-marker").put("customer_phone", "+96800000000").put("items", JSONArray().put(JSONObject().put("product_id", "product-1").put("quantity", 1).put("unit_price", "1.250")))
        val terminal = engine.queue(order.toString())
        var rejected = false
        try { engine.prepareArchive() } catch (expected: Exception) { rejected = true }
        assertTrue(rejected)
        order.put("order_id", UUID.randomUUID().toString()); val pending = engine.queue(order.toString())
        // Synthetic verified-cloud receipt fixture only: not a runtime network/auth bypass.
        val current = reader.invoke(engine) as JSONObject; val entry = current.getJSONObject("orders").getJSONObject(terminal)
        entry.put("state", "native_approved").put("receipt", JSONObject().put("order_id", terminal).put("payload_sha256", entry.getString("hash")).put("native_approval", "approved").put("native_order_id", UUID.randomUUID().toString()))
        writer.invoke(engine, current)
        val bytes = engine.prepareArchive()
        assertFalse(String(bytes, Charsets.ISO_8859_1).contains("archive-private-marker"))
        val decoder = HybridEngine::class.java.getDeclaredMethod("archiveData", ByteArray::class.java).apply { isAccessible = true }
        assertFalse((decoder.invoke(engine, bytes) as JSONObject).toString().contains("never-archive-credential-marker"))
        assertTrue(engine.inspectArchive(bytes).contains(terminal))
        val damaged = bytes.copyOf(); damaged[damaged.lastIndex] = (damaged.last().toInt() xor 1).toByte()
        var tampered = false
        try { engine.confirmArchive(damaged) } catch (expected: Exception) { tampered = true }
        assertTrue(tampered)
        assertEquals(2, (reader.invoke(engine) as JSONObject).getJSONObject("orders").length())
        assertEquals(1, engine.confirmArchive(bytes)); assertEquals(0, engine.confirmArchive(bytes))
        val remaining = (reader.invoke(engine) as JSONObject).getJSONObject("orders")
        assertTrue(remaining.has(pending)); assertFalse(remaining.has(terminal))
    }
    @Test fun corruptArchiveCannotRemoveOrders() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext.also { assertEquals("com.retailgenie.hybrid.pilot.debug", it.packageName) }
        val engine = HybridEngine(context, "test-" + UUID.randomUUID().toString())
        var rejected = false
        try { engine.confirmArchive(ByteArray(128)) } catch (expected: Exception) { rejected = true }
        assertTrue(rejected)
        assertTrue(engine.summary().contains("Retained orders: 0"))
    }

}
