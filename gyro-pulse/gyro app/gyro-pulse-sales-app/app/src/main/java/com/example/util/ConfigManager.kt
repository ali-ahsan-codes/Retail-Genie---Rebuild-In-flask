package com.example.util

import android.content.Context
import android.util.Log
import java.io.File

object ConfigManager {
    private const val TAG = "ConfigManager"
    const val CONFIG_FILE_NAME = "gyropulse.env"

    object Keys {
        const val SERVER_URL = "SERVER_URL"
        const val API_KEY = "API_KEY"
        const val DEVICE_UUID = "DEVICE_UUID"
        const val USER_ID = "USER_ID"
        const val USERNAME = "USERNAME"
        const val ROLE = "ROLE"
        const val CITY_ID = "CITY_ID"
        const val MASTER_SECRET = "MASTER_SECRET"
    }

    /**
     * Get the File reference for gyropulse.env in the app's files directory.
     */
    fun getConfigFile(context: Context): File {
        return File(context.filesDir, CONFIG_FILE_NAME)
    }

    /**
     * Parse .env file format into a Map<String, String>.
     */
    fun parseEnv(content: String): MutableMap<String, String> {
        val config = mutableMapOf<String, String>()
        val lines = content.split("\n")
        for (line in lines) {
            val trimmed = line.trim()
            if (trimmed.isEmpty() || trimmed.startsWith("#")) continue
            val parts = trimmed.split("=", limit = 2)
            if (parts.size == 2) {
                val key = parts[0].trim()
                val value = parts[1].trim()
                if (key.isNotEmpty()) {
                    config[key] = value
                }
            }
        }
        return config
    }

    /**
     * Load configuration map from gyropulse.env if it exists.
     */
    fun loadConfig(context: Context): Map<String, String>? {
        return try {
            val file = getConfigFile(context)
            if (!file.exists()) {
                // Also check external files dir if available
                val extFile = File(context.getExternalFilesDir(null), CONFIG_FILE_NAME)
                if (extFile.exists()) {
                    val content = extFile.readText()
                    return parseEnv(content)
                }
                return null
            }
            val content = file.readText()
            parseEnv(content)
        } catch (e: Exception) {
            Log.e(TAG, "Error loading config from $CONFIG_FILE_NAME", e)
            null
        }
    }

    /**
     * Save configuration map to gyropulse.env file.
     */
    fun saveConfigToFile(context: Context, config: Map<String, String>): Boolean {
        return try {
            val sb = StringBuilder()
            sb.append("# Gyro Pulse Configuration\n")
            sb.append("# Automatically generated & managed\n\n")
            for ((key, value) in config) {
                sb.append("$key=$value\n")
            }
            val file = getConfigFile(context)
            file.writeText(sb.toString())

            // Also keep external files copy synced if accessible
            try {
                val extDir = context.getExternalFilesDir(null)
                if (extDir != null) {
                    File(extDir, CONFIG_FILE_NAME).writeText(sb.toString())
                }
            } catch (_: Exception) {}

            true
        } catch (e: Exception) {
            Log.e(TAG, "Error saving config to $CONFIG_FILE_NAME", e)
            false
        }
    }

    /**
     * Read a specific key from gyropulse.env.
     */
    fun getConfig(context: Context, key: String): String? {
        val config = loadConfig(context)
        return config?.get(key)
    }

    /**
     * Update or set a specific key in gyropulse.env.
     */
    fun setConfig(context: Context, key: String, value: String) {
        val current = loadConfig(context)?.toMutableMap() ?: mutableMapOf()
        current[key] = value
        saveConfigToFile(context, current)
    }

    /**
     * Clear the configuration file.
     */
    fun clearConfig(context: Context) {
        try {
            getConfigFile(context).delete()
            val extDir = context.getExternalFilesDir(null)
            if (extDir != null) {
                File(extDir, CONFIG_FILE_NAME).delete()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error clearing config file", e)
        }
    }
}
