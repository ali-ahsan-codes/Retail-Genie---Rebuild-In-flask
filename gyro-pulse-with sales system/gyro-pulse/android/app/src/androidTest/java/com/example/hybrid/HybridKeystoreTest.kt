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
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val namespace = "test-" + UUID.randomUUID().toString()
        val first = HybridEngine(context, namespace)
        val file = File(context.noBackupFilesDir, "hybrid-state.$namespace")
        assertTrue(file.exists())
        assertFalse(String(file.readBytes(), Charsets.ISO_8859_1).contains(first.deviceId()))
        assertEquals(first.deviceId(), HybridEngine(context, namespace).deviceId())
        assertEquals(first.fingerprint(), HybridEngine(context, namespace).fingerprint())
    }
    @Test fun modifiedCiphertextFailsClosed() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val namespace = "test-" + UUID.randomUUID().toString()
        HybridEngine(context, namespace)
        val file = File(context.noBackupFilesDir, "hybrid-state.$namespace")
        val bytes = file.readBytes(); bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte(); file.writeBytes(bytes)
        var rejected = false
        try { HybridEngine(context, namespace) } catch (expected: Exception) { rejected = true }
        assertTrue(rejected)
    }
    @Test fun immutableQueueEncryptedAcrossRestart() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
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
        val context = InstrumentationRegistry.getInstrumentation().targetContext
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

}
