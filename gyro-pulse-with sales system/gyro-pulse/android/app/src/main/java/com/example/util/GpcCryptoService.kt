package com.example.util

import android.content.Context
import android.util.Base64
import android.util.Log
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import javax.crypto.BadPaddingException
import javax.crypto.Cipher
import javax.crypto.IllegalBlockSizeException
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

object GpcCryptoService {
    private const val TAG = "GpcCryptoService"
    const val DEFAULT_MASTER_SECRET = "b7cae0600eab2ff25c4aaed30a4031f9cfc0e2871d1d11dfa9970877dba0a068"
    private const val ITERATIONS = 100000
    private const val KEY_LENGTH = 256 // bits

    private val FALLBACK_MASTER_SECRETS = listOf(
        DEFAULT_MASTER_SECRET,
        "gyropulse-secret-key-2024",
        "gyropulse-master-secret",
        "gyropulse_secret_key",
        "gyropulse_secret",
        ""
    )

    /**
     * Derive a 256-bit AES key using PBKDF2WithHmacSHA256 (matches backend & React Native crypto).
     */
    fun deriveKey(password: String, salt: ByteArray): SecretKeySpec {
        val spec = PBEKeySpec(password.toCharArray(), salt, ITERATIONS, KEY_LENGTH)
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        val keyBytes = factory.generateSecret(spec).encoded
        return SecretKeySpec(keyBytes, "AES")
    }

    /**
     * Encrypt a JSON payload into GPC binary format (Salt 16B + IV 16B + Ciphertext)
     * and return Base64 encoded string.
     */
    fun encryptPayload(payload: JSONObject, masterSecret: String = DEFAULT_MASTER_SECRET): String {
        val plaintext = payload.toString().toByteArray(StandardCharsets.UTF_8)
        val random = SecureRandom()
        val salt = ByteArray(16)
        val iv = ByteArray(16)
        random.nextBytes(salt)
        random.nextBytes(iv)

        val secretKey = deriveKey(masterSecret, salt)
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey, IvParameterSpec(iv))
        val ciphertext = cipher.doFinal(plaintext)

        val outputStream = ByteArrayOutputStream()
        outputStream.write(salt)
        outputStream.write(iv)
        outputStream.write(ciphertext)
        val combinedBytes = outputStream.toByteArray()

        return Base64.encodeToString(combinedBytes, Base64.NO_WRAP)
    }

    /**
     * Decrypt GPC payload (Base64 string or raw bytes) containing Salt(16) + IV(16) + Ciphertext.
     * Prevents OpenSSL BAD_DECRYPT errors by properly distinguishing raw binary vs Base64 payloads
     * and testing candidate secrets.
     */
    fun decryptPayload(encryptedData: ByteArray, masterSecret: String = DEFAULT_MASTER_SECRET): JSONObject {
        // 1. Fast path: Check if data is already unencrypted plain JSON text
        try {
            val textCandidate = String(encryptedData, StandardCharsets.UTF_8).trim()
            if ((textCandidate.startsWith("{") && textCandidate.endsWith("}")) ||
                (textCandidate.startsWith("[") && textCandidate.endsWith("]"))) {
                return JSONObject(textCandidate)
            }
        } catch (_: Exception) {}

        // 2. Build candidate byte arrays (raw binary vs base64 decoded vs hex)
        val candidateByteArrays = mutableListOf<ByteArray>()

        // Candidate A: Raw binary bytes directly (if valid ciphertext length)
        if (encryptedData.size >= 32) {
            candidateByteArrays.add(encryptedData)
        }

        // Candidate B: Try Base64 decoding if the input looks like ASCII Base64
        try {
            val asAscii = String(encryptedData, StandardCharsets.US_ASCII).trim()
            val decoded = Base64.decode(asAscii, Base64.DEFAULT)
            if (decoded != null && decoded.size >= 32 && !decoded.contentEquals(encryptedData)) {
                // Prioritize base64 decoded bytes if the original data was printable ASCII
                val isPrintableAscii = encryptedData.all { it in 32..126 || it == 10.toByte() || it == 13.toByte() }
                if (isPrintableAscii) {
                    candidateByteArrays.add(0, decoded)
                } else {
                    candidateByteArrays.add(decoded)
                }
            }
        } catch (_: Exception) {}

        // Candidate C: Hex decode if hex string
        try {
            val asHex = String(encryptedData, StandardCharsets.US_ASCII).trim()
            if (asHex.length >= 64 && asHex.length % 2 == 0 && asHex.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' }) {
                val hexBytes = ByteArray(asHex.length / 2) { i ->
                    asHex.substring(i * 2, i * 2 + 2).toInt(16).toByte()
                }
                candidateByteArrays.add(hexBytes)
            }
        } catch (_: Exception) {}

        // 3. Build candidate master secrets list
        val candidateSecrets = LinkedHashSet<String>()
        if (masterSecret.isNotEmpty()) candidateSecrets.add(masterSecret)
        candidateSecrets.addAll(FALLBACK_MASTER_SECRETS)

        var lastException: Exception? = null

        // 4. Try decrypting across candidate byte arrays and candidate keys
        for (candidateBytes in candidateByteArrays) {
            if (candidateBytes.size < 32) continue
            val salt = candidateBytes.copyOfRange(0, 16)
            val iv = candidateBytes.copyOfRange(16, 32)
            val ciphertext = candidateBytes.copyOfRange(32, candidateBytes.size)

            if (ciphertext.isEmpty() || ciphertext.size % 16 != 0) continue

            for (secret in candidateSecrets) {
                try {
                    val secretKey = deriveKey(secret, salt)
                    val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
                    cipher.init(Cipher.DECRYPT_MODE, secretKey, IvParameterSpec(iv))
                    val decryptedBytes = cipher.doFinal(ciphertext)
                    val jsonString = String(decryptedBytes, StandardCharsets.UTF_8).trim()

                    if (jsonString.startsWith("{") && jsonString.endsWith("}")) {
                        Log.d(TAG, "Successfully decrypted GPC payload with key length: ${secret.length}")
                        return JSONObject(jsonString)
                    }
                } catch (e: BadPaddingException) {
                    // Wrong key or padding mismatch, try next secret
                    lastException = e
                } catch (e: IllegalBlockSizeException) {
                    lastException = e
                } catch (e: Exception) {
                    lastException = e
                }
            }
        }

        // If decryption failed, check if the file can be parsed as a plain JSON string fallback
        try {
            val fallbackString = String(encryptedData, StandardCharsets.UTF_8).trim()
            if (fallbackString.contains("{") && fallbackString.contains("}")) {
                val start = fallbackString.indexOf("{")
                val end = fallbackString.lastIndexOf("}")
                if (start in 0 until end) {
                    val sub = fallbackString.substring(start, end + 1)
                    return JSONObject(sub)
                }
            }
        } catch (_: Exception) {}

        throw IllegalStateException(
            "Failed to decrypt .gpc file. Please verify the master secret matches the server encryption key. (${lastException?.message ?: "Invalid ciphertext or padding"})",
            lastException
        )
    }
}

