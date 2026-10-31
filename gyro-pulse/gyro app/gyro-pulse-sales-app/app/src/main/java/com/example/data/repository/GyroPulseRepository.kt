package com.example.data.repository

import android.content.Context
import android.net.Uri
import android.webkit.MimeTypeMap
import com.example.data.local.Message
import com.example.data.local.MessageDao
import com.example.data.local.InboxMessageDao
import com.example.data.local.InboxMessageEntity
import com.example.data.local.GyroPulsePreferences
import com.example.data.remote.RetrofitClient
import com.example.data.remote.ProductResponse
import com.example.data.remote.CustomerResponse
import com.example.data.remote.OrderItemRequest
import com.example.data.remote.OrderPlaceResponse
import com.example.data.remote.SettingsResponse
import kotlinx.coroutines.flow.Flow
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.UUID

class GyroPulseRepository(
    private val context: Context,
    val messageDao: MessageDao,
    private val inboxMessageDao: InboxMessageDao,
    private val prefs: GyroPulsePreferences
) {
    val allMessages: Flow<List<Message>> = messageDao.getAllMessagesFlow()
    val allInboxMessages: Flow<List<InboxMessageEntity>> = inboxMessageDao.getAllInboxMessagesFlow()

    fun getPreferences(): GyroPulsePreferences = prefs

    fun resetClient() {
        RetrofitClient.reset()
    }

    sealed interface LoginResult {
        object Success : LoginResult
        object InvalidCredentials : LoginResult
        object NetworkError : LoginResult
        data class ServerError(val message: String) : LoginResult
        object CityMissing : LoginResult
    }

    suspend fun login(username: String, password: String): LoginResult {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val jsonReq = JSONObject().apply {
                put("username", username)
                put("password", password)
            }
            val requestBody = jsonReq.toString().toRequestBody("application/json".toMediaTypeOrNull())
            val responseBody = api.login(requestBody)
            val responseString = responseBody.string()
            val responseJson = JSONObject(responseString)

            val apiKey = responseJson.optString("api_key", "")
            val userId = responseJson.optInt("user_id", -1)
            val role = responseJson.optString("role", "")
            val cityId = if (responseJson.has("city_id") && !responseJson.isNull("city_id")) responseJson.getInt("city_id") else null
            val returnedUsername = responseJson.optString("username", "")

            if (apiKey.isNotEmpty()) {
                prefs.setApiKey(apiKey)
            }
            if (userId != -1) {
                prefs.setUserId(userId)
            }
            if (role.isNotEmpty()) {
                prefs.setRole(role)
            }
            prefs.setCityId(cityId) // Always update cityId, could be null
            if (returnedUsername.isNotEmpty()) {
                prefs.setDeviceName(returnedUsername)
            }
            resetClient()

            // Check if city_id is null and role is not admin/subadmin
            if (cityId == null && role !in listOf("admin", "subadmin")) {
                return LoginResult.CityMissing
            }

            LoginResult.Success
        } catch (e: retrofit2.HttpException) {
            e.printStackTrace()
            if (e.code() == 401 || e.code() == 403) {
                LoginResult.InvalidCredentials
            } else {
                LoginResult.ServerError(e.message() ?: "HTTP ${e.code()}")
            }
        } catch (e: Exception) {
            e.printStackTrace()
            LoginResult.NetworkError
        }
    }

    suspend fun fetchSettings(): SettingsResponse? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val response = api.getSettings()
            val json = JSONObject(response.string())
            SettingsResponse(
                currency = json.optString("currency", "$"),
                tax_rate = json.optDouble("tax_rate", 0.0),
                tax_label = json.optString("tax_label", "Tax")
            )
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun pingAndSaveUser(): Boolean {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val responseBody = api.ping(prefs.getUserId())
            val responseJson = JSONObject(responseBody.string())
            
            var userId = responseJson.optInt("user_id", -1)
            if (userId == -1) {
                userId = responseJson.optInt("id", -1)
            }
            if (userId == -1) {
                userId = responseJson.optInt("userId", -1)
            }
            if (userId == -1) {
                userId = responseJson.optInt("uid", -1)
            }
            if (userId == -1 && responseJson.has("user")) {
                val userObj = responseJson.optJSONObject("user")
                if (userObj != null) {
                    userId = userObj.optInt("id", -1)
                    if (userId == -1) {
                        userId = userObj.optInt("user_id", -1)
                    }
                }
            }
            
            if (userId != -1) {
                prefs.setUserId(userId)
            } else {
                if (prefs.getUserId() == null) {
                    prefs.setUserId(1) // Default/fallback userId
                }
            }
            
            val status = responseJson.optString("status", "")
            status == "ok" || status == "success" || responseJson.has("user_id") || responseJson.has("id")
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun pingServer(): Boolean {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val responseBody = api.ping(prefs.getUserId())
            val responseJson = JSONObject(responseBody.string())
            val status = responseJson.optString("status", "")
            status == "ok" || status == "success" || responseJson.has("user_id")
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun insertLocalMessage(
        type: String,
        content: String?,
        mediaUri: String?,
        latitude: Double?,
        longitude: Double?
    ): Long {
        val message = Message(
            type = type,
            content = content,
            mediaUri = mediaUri,
            latitude = latitude,
            longitude = longitude,
            createdAt = System.currentTimeMillis(),
            synced = false
        )
        return messageDao.insert(message)
    }

    suspend fun uploadMessageImmediately(messageId: Long): Boolean {
        val pendingList = messageDao.getPendingMessages()
        val message = pendingList.find { it.id == messageId } ?: return false
        
        return try {
            val api = RetrofitClient.getApi(prefs)

            val apiType = mapUiTypeToApiType(message.type)
            val typeBody = apiType.toRequestBody("text/plain".toMediaTypeOrNull())
            val contentBody = message.content?.toRequestBody("text/plain".toMediaTypeOrNull())
            val latBody = message.latitude?.toString()?.toRequestBody("text/plain".toMediaTypeOrNull())
            val lonBody = message.longitude?.toString()?.toRequestBody("text/plain".toMediaTypeOrNull())
            val deviceIdBody = prefs.getDeviceId().toRequestBody("text/plain".toMediaTypeOrNull())
            val userIdBody = (prefs.getUserId() ?: -1).toString().toRequestBody("text/plain".toMediaTypeOrNull())

            val filePart = message.mediaUri?.let { path ->
                val file = File(path)
                if (file.exists()) {
                    val ext = MimeTypeMap.getFileExtensionFromUrl(path) ?: "bin"
                    val mimeType = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "application/octet-stream"
                    val requestFile = file.asRequestBody(mimeType.toMediaTypeOrNull())
                    MultipartBody.Part.createFormData("file", file.name, requestFile)
                } else null
            }

            val responseBody = api.sendMessage(
                type = typeBody,
                content = contentBody,
                latitude = latBody,
                longitude = lonBody,
                deviceId = deviceIdBody,
                userId = userIdBody,
                file = filePart
            )

            val responseJson = JSONObject(responseBody.string())
            val status = responseJson.optString("status", "")
            val serverId = responseJson.optInt("message_id", -1)

            if (status == "success" || serverId != -1) {
                messageDao.updateSyncStatus(
                    id = message.id,
                    synced = true,
                    serverId = if (serverId != -1) serverId else null
                )
                true
            } else {
                false
            }
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun performBatchSync(): Boolean {
        val pending = messageDao.getPendingMessages()
        if (pending.isEmpty()) return true

        return try {
            val api = RetrofitClient.getApi(prefs)
            
            val jsonRequest = JSONObject().apply {
                put("user_id", prefs.getUserId() ?: -1)
                
                val jsonArray = JSONArray()
                pending.forEach { msg ->
                    val item = JSONObject().apply {
                        put("type", mapUiTypeToApiType(msg.type))
                        put("content", msg.content ?: if (msg.mediaUri != null) "Media File" else null)
                        if (msg.latitude != null) put("latitude", msg.latitude)
                        if (msg.longitude != null) put("longitude", msg.longitude)
                        put("device_id", prefs.getDeviceId())
                        put("created_at", msg.createdAt)
                    }
                    jsonArray.put(item)
                }
                put("messages", jsonArray)
            }

            val requestBody = jsonRequest.toString().toRequestBody("application/json".toMediaTypeOrNull())
            val responseBody = api.syncMessages(requestBody)
            val responseJson = JSONObject(responseBody.string())

            val acceptedJson = responseJson.optJSONArray("accepted")
            val failedJson = responseJson.optJSONArray("failed")

            val acceptedIds = mutableListOf<Int>()
            if (acceptedJson != null) {
                for (i in 0 until acceptedJson.length()) {
                    acceptedIds.add(acceptedJson.getInt(i))
                }
            }

            val failedIndices = mutableSetOf<Int>()
            if (failedJson != null) {
                for (i in 0 until failedJson.length()) {
                    failedIndices.add(failedJson.getInt(i))
                }
            }

            pending.forEachIndexed { index, message ->
                if (!failedIndices.contains(index)) {
                    val serverId = acceptedIds.getOrNull(index) ?: 0
                    messageDao.updateSyncStatus(message.id, true, serverId)
                }
            }
            true
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun fetchAdminReplies(): Boolean {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val responseBody = api.getResponses(20)
            val responseJson = JSONObject(responseBody.string())
            val dataArray = responseJson.optJSONArray("data") ?: return true
            
            val messagesToInsert = mutableListOf<Message>()
            for (i in 0 until dataArray.length()) {
                val replyObj = dataArray.getJSONObject(i)
                val id = replyObj.getInt("id")
                val message = replyObj.getString("message")
                val mediaUrl = replyObj.optString("media_url", null)
                val absoluteMediaUrl = getAbsoluteMediaUrl(mediaUrl)
                val createdAtStr = replyObj.getString("created_at")

                messagesToInsert.add(
                    Message(
                        type = "text",
                        content = null,
                        mediaUri = absoluteMediaUrl,
                        latitude = null,
                        longitude = null,
                        createdAt = parseIso8601ToMillis(createdAtStr),
                        synced = true,
                        serverId = id,
                        isReply = true,
                        replyMessage = message
                    )
                )
            }
            messageDao.insertAll(messagesToInsert)
            true
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    fun saveFileToInternalStorage(uri: Uri, extension: String): String? {
        return try {
            val contentResolver = context.contentResolver
            val inputStream = contentResolver.openInputStream(uri) ?: return null
            val fileName = "media_${UUID.randomUUID()}.$extension"
            val file = File(context.filesDir, fileName)
            val outputStream = FileOutputStream(file)
            
            inputStream.copyTo(outputStream)
            inputStream.close()
            outputStream.close()
            
            val maxSize = 9 * 1024 * 1024
            if (file.length() > maxSize) {
                file.delete()
                throw IllegalArgumentException("File size exceeds 9 MB limit.")
            }
            
            file.absolutePath
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    fun createLocalFileForRecording(extension: String): File {
        val fileName = "rec_${UUID.randomUUID()}.$extension"
        return File(context.filesDir, fileName)
    }

    private fun parseIso8601ToMillis(dateStr: String): Long {
        return try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                java.time.Instant.parse(dateStr).toEpochMilli()
            } else {
                val sdf = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US)
                sdf.timeZone = java.util.TimeZone.getTimeZone("UTC")
                sdf.parse(dateStr)?.time ?: System.currentTimeMillis()
            }
        } catch (e: Exception) {
            System.currentTimeMillis()
        }
    }

    private fun mapUiTypeToApiType(uiType: String): String {
        return when (uiType.lowercase()) {
            "text" -> "data"
            "barcode" -> "data"
            "voice" -> "audio"
            "image" -> "picture"
            else -> uiType
        }
    }

    private fun getAbsoluteMediaUrl(relativeUrl: String?): String? {
        if (relativeUrl.isNullOrEmpty() || relativeUrl == "null") return null
        if (relativeUrl.startsWith("http://") || relativeUrl.startsWith("https://")) {
            return relativeUrl
        }
        val baseUrl = prefs.getServerUrl().trimEnd('/')
        val normalizedRelativeUrl = if (relativeUrl.startsWith("/")) relativeUrl else "/$relativeUrl"
        return baseUrl + normalizedRelativeUrl
    }

    suspend fun fetchInbox(userId: Int, limit: Int = 20, offset: Int = 0): Boolean {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val responseBody = api.getInbox(userId = userId, limit = limit, offset = offset)
            val responseJson = JSONObject(responseBody.string())
            val messagesArray = responseJson.optJSONArray("messages") ?: return true
            
            val entities = mutableListOf<InboxMessageEntity>()
            for (i in 0 until messagesArray.length()) {
                val obj = messagesArray.getJSONObject(i)
                val id = obj.getInt("id")
                val senderId = obj.getInt("sender_id")
                val senderUsername = obj.optString("sender_username", "Unknown")
                val content = obj.optString("content", null)
                val mediaUrl = obj.optString("media_url", null)
                val createdAt = obj.getString("created_at")
                val read = obj.optBoolean("read", false)
                
                entities.add(
                    InboxMessageEntity(
                        id = id,
                        senderId = senderId,
                        senderUsername = senderUsername,
                        content = if (content == "null" || content.isEmpty()) null else content,
                        mediaUrl = if (mediaUrl == "null" || mediaUrl.isEmpty()) null else mediaUrl,
                        createdAt = createdAt,
                        read = read
                    )
                )
            }
            inboxMessageDao.insertAll(entities)
            true
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    suspend fun markInboxMessageAsRead(id: Int): Boolean {
        return try {
            val api = RetrofitClient.getApi(prefs)
            api.markMessageRead(id)
            inboxMessageDao.markAsRead(id)
            true
        } catch (e: Exception) {
            e.printStackTrace()
            inboxMessageDao.markAsRead(id)
            false
        }
    }

    suspend fun pollNewMessages(userId: Int, since: String?): List<Message>? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val responseBody = api.pollMessages(userId, since)
            val json = JSONObject(responseBody.string())
            val messagesArray = json.optJSONArray("messages") ?: return emptyList()
            val result = mutableListOf<Message>()
            for (i in 0 until messagesArray.length()) {
                val obj = messagesArray.getJSONObject(i)
                val createdAt = obj.getString("created_at")
                val millis = parseIso8601ToMillis(createdAt)
                val mediaUrl = obj.optString("media_url", null)
                val absoluteMediaUrl = getAbsoluteMediaUrl(mediaUrl)
                result.add(Message(
                    type = obj.getString("type"),
                    content = obj.optString("content", null),
                    mediaUri = absoluteMediaUrl,
                    latitude = if (obj.has("latitude") && !obj.isNull("latitude")) obj.getDouble("latitude") else null,
                    longitude = if (obj.has("longitude") && !obj.isNull("longitude")) obj.getDouble("longitude") else null,
                    createdAt = millis,
                    synced = true,
                    serverId = obj.getInt("id"),
                    isReply = false,
                    replyMessage = null
                ))
            }
            result
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun checkSyncStatus(userId: Int): SyncStatus? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val responseBody = api.getSyncStatus(userId)
            val json = JSONObject(responseBody.string())
            SyncStatus(
                uploadRequired = json.optBoolean("upload_required", false),
                lastMessageTimestamp = json.optString("last_message_timestamp", null)
            )
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    data class SyncStatus(
        val uploadRequired: Boolean,
        val lastMessageTimestamp: String?
    )

    suspend fun uploadAllMessages(userId: Int): UploadAllResult? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val allMessages = messageDao.getAllMessages()
            if (allMessages.isEmpty()) {
                return UploadAllResult(success = true, inserted = 0, mapping = emptyMap())
            }

            val jsonRequest = JSONObject().apply {
                put("user_id", userId)
                val jsonArray = JSONArray()
                allMessages.forEach { msg ->
                    val item = JSONObject().apply {
                        put("client_id", msg.id.toString())
                        put("type", mapUiTypeToApiType(msg.type))
                        put("content", msg.content ?: if (msg.mediaUri != null) "Media File" else null)
                        if (msg.latitude != null) put("latitude", msg.latitude)
                        if (msg.longitude != null) put("longitude", msg.longitude)
                        put("device_id", prefs.getDeviceId())
                        put("created_at", java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US)
                            .format(java.util.Date(msg.createdAt)))
                    }
                    jsonArray.put(item)
                }
                put("messages", jsonArray)
            }

            val requestBody = jsonRequest.toString().toRequestBody("application/json".toMediaTypeOrNull())
            val responseBody = api.uploadAllMessages(requestBody)
            val responseJson = JSONObject(responseBody.string())
            val status = responseJson.optString("status", "")
            val inserted = responseJson.optInt("inserted", 0)
            val mappingObj = responseJson.optJSONObject("mapping")

            val mapping = mutableMapOf<Long, Int>()
            if (mappingObj != null) {
                val keys = mappingObj.keys()
                while (keys.hasNext()) {
                    val clientId = keys.next()
                    val serverId = mappingObj.getInt(clientId)
                    mapping[clientId.toLong()] = serverId
                }
            }

            mapping.forEach { (clientId, serverId) ->
                messageDao.updateServerId(clientId, serverId)
                messageDao.updateSyncStatus(clientId, true, serverId)
            }

            UploadAllResult(success = status == "success", inserted = inserted, mapping = mapping)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    data class UploadAllResult(
        val success: Boolean,
        val inserted: Int,
        val mapping: Map<Long, Int>
    )

    suspend fun fetchHistoricalMessages(userId: Int, from: String?, to: String?, type: String?): List<Message>? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val responseBody = api.exportUserMessages(userId, from, to, type)
            val responseJson = JSONObject(responseBody.string())
            val messagesArray = responseJson.optJSONArray("messages") ?: return emptyList()
            val result = mutableListOf<Message>()
            for (i in 0 until messagesArray.length()) {
                val obj = messagesArray.getJSONObject(i)
                val createdAt = obj.getString("created_at")
                val millis = parseIso8601ToMillis(createdAt)
                val mediaUrl = obj.optString("media_url", null)
                val absoluteMediaUrl = getAbsoluteMediaUrl(mediaUrl)
                result.add(Message(
                    type = obj.getString("type"),
                    content = obj.optString("content", null),
                    mediaUri = absoluteMediaUrl,
                    latitude = if (obj.has("latitude") && !obj.isNull("latitude")) obj.getDouble("latitude") else null,
                    longitude = if (obj.has("longitude") && !obj.isNull("longitude")) obj.getDouble("longitude") else null,
                    createdAt = millis,
                    synced = true,
                    serverId = obj.getInt("id"),
                    isReply = false,
                    replyMessage = null
                ))
            }
            result
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun importHistoricalMessages(messages: List<Message>): Int {
        val existingIds = messageDao.getAllServerIds().toSet()
        val toInsert = messages.filter { it.serverId !in existingIds }
        if (toInsert.isNotEmpty()) {
            messageDao.insertAll(toInsert)
        }
        return toInsert.size
    }

    // ---------- NEW SALES METHODS ----------
    suspend fun syncProducts(since: String? = null, cityId: Int? = null): Pair<List<ProductResponse>, String>? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val userId = prefs.getUserId() ?: return null
            val response = api.syncProducts(userId, since, cityId)
            val json = JSONObject(response.string())
            val array = json.optJSONArray("products") ?: JSONArray()
            val list = mutableListOf<ProductResponse>()
            for (i in 0 until array.length()) {
                val obj = array.getJSONObject(i)
                list.add(ProductResponse(
                    id = obj.getInt("id"),
                    name = obj.getString("name"),
                    sku = obj.optString("sku", null),
                    barcode = obj.optString("barcode", null),
                    unit_price = obj.getDouble("unit_price"),
                    tax_rate = obj.optDouble("tax_rate", 0.05),
                    current_warehouse_qty = obj.optInt("current_warehouse_qty", 0),
                    description = obj.optString("description", null),
                    image_url = obj.optString("image_url", null),
                    is_active = obj.optBoolean("is_active", true)
                ))
            }
            val timestamp = json.optString("timestamp", "")
            Pair(list, timestamp)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun searchProducts(query: String?, barcode: String?): List<ProductResponse>? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val userId = prefs.getUserId() ?: return null
            val response = api.searchProducts(userId, query, barcode)
            val json = JSONObject(response.string())
            val array = json.optJSONArray("products") ?: return emptyList()
            val list = mutableListOf<ProductResponse>()
            for (i in 0 until array.length()) {
                val obj = array.getJSONObject(i)
                list.add(ProductResponse(
                    id = obj.getInt("id"),
                    name = obj.getString("name"),
                    sku = obj.optString("sku", null),
                    barcode = obj.optString("barcode", null),
                    unit_price = obj.getDouble("unit_price"),
                    tax_rate = obj.optDouble("tax_rate", 0.05),
                    current_warehouse_qty = obj.optInt("current_warehouse_qty", 0),
                    description = obj.optString("description", null),
                    image_url = obj.optString("image_url", null),
                    is_active = obj.optBoolean("is_active", true)
                ))
            }
            list
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun searchCustomers(query: String): List<CustomerResponse>? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val userId = prefs.getUserId() ?: return null
            val response = api.searchCustomers(userId, query)
            val json = JSONObject(response.string())
            val array = json.optJSONArray("customers") ?: return emptyList()
            val list = mutableListOf<CustomerResponse>()
            for (i in 0 until array.length()) {
                val obj = array.getJSONObject(i)
                list.add(CustomerResponse(
                    id = obj.getInt("id"),
                    name = obj.getString("name"),
                    phone = obj.getString("phone"),
                    email = obj.optString("email", null),
                    billing_address = obj.optString("billing_address", null),
                    shipping_address = obj.optString("shipping_address", null),
                    outstanding_balance = obj.optDouble("outstanding_balance", 0.0)
                ))
            }
            list
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun createCustomer(name: String, phone: String, address: String?): CustomerResponse? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val json = JSONObject().apply {
                put("name", name)
                put("phone", phone)
                put("shipping_address", address ?: "")
            }
            val body = json.toString().toRequestBody("application/json".toMediaTypeOrNull())
            val response = api.createCustomer(body)
            val jsonResp = JSONObject(response.string())
            val obj = jsonResp.getJSONObject("customer")
            CustomerResponse(
                id = obj.getInt("id"),
                name = obj.getString("name"),
                phone = obj.getString("phone"),
                email = obj.optString("email", null),
                billing_address = obj.optString("billing_address", null),
                shipping_address = obj.optString("shipping_address", null),
                outstanding_balance = 0.0
            )
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun placeOrder(
        customerId: Int?,
        customerName: String,
        customerPhone: String,
        shippingAddress: String?,
        latitude: Double?,
        longitude: Double?,
        items: List<OrderItemRequest>,
        subtotal: Double,
        taxAmount: Double,
        discount: Double,
        netTotal: Double,
        paidAmount: Double,
        paymentTerms: String?,
        specialInstructions: String?,
        files: List<File>? = null  // Not used, kept for compatibility
    ): OrderPlaceResponse? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val json = JSONObject().apply {
                put("customer_id", customerId ?: JSONObject.NULL)
                put("customer_name", customerName)
                put("customer_phone", customerPhone)
                put("shipping_address", shippingAddress ?: "")
                put("latitude", latitude ?: JSONObject.NULL)
                put("longitude", longitude ?: JSONObject.NULL)
                put("items", JSONArray().apply {
                    items.forEach { item ->
                        put(JSONObject().apply {
                            put("product_id", item.product_id)
                            put("quantity", item.qty)
                            put("unit_price", item.unit_price)
                            item.note?.let { put("note", it) }
                        })
                    }
                })
                put("subtotal", subtotal)
                put("tax_amount", taxAmount)
                put("discount", discount)
                put("net_total", netTotal)
                put("paid_amount", paidAmount)
                put("payment_terms", paymentTerms ?: "")
                put("special_instructions", specialInstructions ?: "")
            }
            val requestBody = json.toString().toRequestBody("application/json".toMediaTypeOrNull())
            val response = api.placeOrder(requestBody)
            val responseJson = JSONObject(response.string())
            OrderPlaceResponse(
                status = responseJson.getString("status"),
                order_id = responseJson.getInt("order_id"),
                message = responseJson.optString("message", "Success")
            )
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun syncMobile(): JSONObject? {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val response = api.mobileSync()
            val json = JSONObject(response.string())

            // Auto refill tokens if returned
            if (json.has("new_tokens")) {
                val arr = json.getJSONArray("new_tokens")
                val tokens = mutableListOf<String>()
                for (i in 0 until arr.length()) {
                    tokens.add(arr.getString(i))
                }
                prefs.addTokens(tokens)
            }

            // Process remote commands
            if (json.has("commands")) {
                val cmds = json.getJSONArray("commands")
                val executedIds = mutableListOf<Int>()
                for (i in 0 until cmds.length()) {
                    val cmd = cmds.getJSONObject(i)
                    val cmdId = cmd.optInt("id", -1)
                    val cmdType = cmd.optString("command_type", "")
                    if (cmdType == "DELETE_MEDIA" && cmd.has("payload")) {
                        val payload = cmd.getJSONObject("payload")
                        val mediaUuids = payload.optJSONArray("media_uuids")
                        if (mediaUuids != null) {
                            for (j in 0 until mediaUuids.length()) {
                                val uuid = mediaUuids.getString(j)
                                val file = File(context.filesDir, "media/$uuid")
                                if (file.exists()) file.delete()
                            }
                        }
                    }
                    if (cmdId != -1) executedIds.add(cmdId)
                }
                if (executedIds.isNotEmpty()) {
                    acknowledgeCommands(executedIds)
                }
            }
            json
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    suspend fun acknowledgeCommands(commandIds: List<Int>): Boolean {
        return try {
            val api = RetrofitClient.getApi(prefs)
            val body = JSONObject().apply {
                put("command_ids", JSONArray(commandIds))
            }.toString().toRequestBody("application/json".toMediaTypeOrNull())
            api.acknowledgeCommands(body)
            true
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }
}

