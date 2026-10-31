package com.example.data.local

import android.content.Context
import android.content.SharedPreferences
import com.example.util.ConfigManager
import org.json.JSONArray
import java.util.UUID

class GyroPulsePreferences(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("gyropulse_prefs", Context.MODE_PRIVATE)

    companion object {
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_API_KEY = "api_key"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_USER_ID = "user_id"
        private const val KEY_ROLE = "role"
        private const val KEY_CITY_ID = "city_id"
        private const val KEY_TOKENS = "tokens_list"
        private const val KEY_SESSION_ID = "session_id"
        private const val KEY_LAST_POLL_TIMESTAMP = "last_poll_timestamp"
        private const val KEY_LAST_PRODUCT_SYNC = "last_product_sync"
        private const val DEFAULT_SERVER_URL = "https://app2.gyropulse.com/"
    }

    init {
        // Load initial config from gyropulse.env if preferences are empty
        loadFromEnvConfig()

        if (getDeviceId().isEmpty()) {
            val randomId = UUID.randomUUID().toString().take(8)
            prefs.edit().putString(KEY_DEVICE_ID, "dev_$randomId").apply()
            syncToEnvConfig()
        }
    }

    private fun loadFromEnvConfig() {
        val env = ConfigManager.loadConfig(context) ?: return
        val currentApiKey = prefs.getString(KEY_API_KEY, null)
        if (currentApiKey.isNullOrEmpty()) {
            val envApiKey = env[ConfigManager.Keys.API_KEY]
            val envServerUrl = env[ConfigManager.Keys.SERVER_URL]
            val envDeviceId = env[ConfigManager.Keys.DEVICE_UUID]
            val envUserId = env[ConfigManager.Keys.USER_ID]?.toIntOrNull()
            val envRole = env[ConfigManager.Keys.ROLE]
            val envCityId = env[ConfigManager.Keys.CITY_ID]?.toIntOrNull()

            val editor = prefs.edit()
            if (!envApiKey.isNullOrEmpty()) editor.putString(KEY_API_KEY, envApiKey)
            if (!envServerUrl.isNullOrEmpty()) editor.putString(KEY_SERVER_URL, envServerUrl)
            if (!envDeviceId.isNullOrEmpty()) editor.putString(KEY_DEVICE_ID, envDeviceId)
            if (envUserId != null && envUserId != -1) editor.putInt(KEY_USER_ID, envUserId)
            if (!envRole.isNullOrEmpty()) editor.putString(KEY_ROLE, envRole)
            if (envCityId != null && envCityId != -1) editor.putInt(KEY_CITY_ID, envCityId)
            editor.apply()
        }
    }

    fun syncToEnvConfig() {
        val map = mutableMapOf<String, String>()
        map[ConfigManager.Keys.SERVER_URL] = getServerUrl()
        getApiKey()?.let { map[ConfigManager.Keys.API_KEY] = it }
        map[ConfigManager.Keys.DEVICE_UUID] = getDeviceId()
        getUserId()?.let { map[ConfigManager.Keys.USER_ID] = it.toString() }
        map[ConfigManager.Keys.USERNAME] = getDeviceName()
        getRole()?.let { map[ConfigManager.Keys.ROLE] = it }
        getCityId()?.let { map[ConfigManager.Keys.CITY_ID] = it.toString() }
        ConfigManager.saveConfigToFile(context, map)
    }

    fun getServerUrl(): String = prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
    fun setServerUrl(url: String) {
        var formattedUrl = url.trim()
        if (!formattedUrl.startsWith("http://") && !formattedUrl.startsWith("https://")) {
            formattedUrl = "https://$formattedUrl"
        }
        if (!formattedUrl.endsWith("/")) formattedUrl += "/"
        prefs.edit().putString(KEY_SERVER_URL, formattedUrl).apply()
        syncToEnvConfig()
    }

    fun getApiKey(): String? = prefs.getString(KEY_API_KEY, null)
    fun setApiKey(key: String?) {
        prefs.edit().putString(KEY_API_KEY, key).apply()
        syncToEnvConfig()
    }

    fun getUserId(): Int? {
        val id = prefs.getInt(KEY_USER_ID, -1)
        if (id != -1) return id
        return if (!getApiKey().isNullOrEmpty()) 1 else null
    }
    fun setUserId(id: Int?) {
        if (id == null) prefs.edit().remove(KEY_USER_ID).apply()
        else prefs.edit().putInt(KEY_USER_ID, id).apply()
        syncToEnvConfig()
    }

    fun getRole(): String? = prefs.getString(KEY_ROLE, null)
    fun setRole(role: String?) {
        prefs.edit().putString(KEY_ROLE, role).apply()
        syncToEnvConfig()
    }

    fun getCityId(): Int? {
        val id = prefs.getInt(KEY_CITY_ID, -1)
        return if (id != -1) id else null
    }
    fun setCityId(id: Int?) {
        if (id == null) prefs.edit().remove(KEY_CITY_ID).apply()
        else prefs.edit().putInt(KEY_CITY_ID, id).apply()
        syncToEnvConfig()
    }

    fun getDeviceName(): String = prefs.getString(KEY_DEVICE_NAME, "Sales Rep") ?: "Sales Rep"
    fun setDeviceName(name: String) {
        prefs.edit().putString(KEY_DEVICE_NAME, name).apply()
        syncToEnvConfig()
    }

    fun getDeviceId(): String = prefs.getString(KEY_DEVICE_ID, "") ?: ""

    fun getSessionId(): String? = prefs.getString(KEY_SESSION_ID, null)
    fun setSessionId(id: String?) = prefs.edit().putString(KEY_SESSION_ID, id).apply()

    fun getTokens(): List<String> {
        val json = prefs.getString(KEY_TOKENS, null) ?: return emptyList()
        return try {
            val arr = JSONArray(json)
            List(arr.length()) { arr.getString(it) }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun setTokens(tokens: List<String>) {
        val arr = JSONArray()
        tokens.forEach { arr.put(it) }
        prefs.edit().putString(KEY_TOKENS, arr.toString()).apply()
    }

    fun addTokens(newTokens: List<String>) {
        val current = getTokens().toMutableList()
        current.addAll(newTokens)
        setTokens(current)
    }

    fun useToken(): String? {
        val current = getTokens().toMutableList()
        if (current.isNotEmpty()) {
            val token = current.removeAt(0)
            setTokens(current)
            return token
        }
        return null
    }

    fun getLastPollTimestamp(): String? = prefs.getString(KEY_LAST_POLL_TIMESTAMP, null)
    fun setLastPollTimestamp(timestamp: String) = prefs.edit().putString(KEY_LAST_POLL_TIMESTAMP, timestamp).apply()

    fun getLastProductSyncTimestamp(): String? = prefs.getString(KEY_LAST_PRODUCT_SYNC, null)
    fun setLastProductSyncTimestamp(timestamp: String) = prefs.edit().putString(KEY_LAST_PRODUCT_SYNC, timestamp).apply()

    fun isRegistered(): Boolean = !getApiKey().isNullOrEmpty()

    fun clear() {
        prefs.edit()
            .remove(KEY_API_KEY)
            .remove(KEY_USER_ID)
            .remove(KEY_ROLE)
            .remove(KEY_CITY_ID)
            .remove(KEY_TOKENS)
            .remove(KEY_SESSION_ID)
            .remove(KEY_LAST_POLL_TIMESTAMP)
            .remove(KEY_LAST_PRODUCT_SYNC)
            .apply()
        ConfigManager.clearConfig(context)
    }
}
