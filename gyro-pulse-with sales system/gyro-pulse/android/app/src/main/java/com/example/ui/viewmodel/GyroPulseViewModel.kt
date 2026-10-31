package com.example.ui.viewmodel

import android.annotation.SuppressLint
import android.content.Context
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.data.local.AppDatabase
import com.example.data.local.Message
import com.example.data.local.InboxMessageEntity
import com.example.data.local.GyroPulsePreferences
import kotlinx.coroutines.delay
import com.example.data.repository.GyroPulseRepository
import com.example.data.remote.ProductResponse
import com.example.data.remote.CustomerResponse
import com.example.data.remote.OrderItemRequest
import com.example.data.remote.OrderPlaceResponse
import com.example.data.remote.SettingsResponse
import com.google.android.gms.location.LocationServices
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.io.File
import kotlin.coroutines.resume
import com.example.util.BackupManager
import com.example.util.ConfigManager
import com.example.util.GpcCryptoService
import org.json.JSONArray
import org.json.JSONObject
import androidx.core.content.FileProvider
import android.util.Log

class GyroPulseViewModel(
    private val context: Context,
    private val repository: GyroPulseRepository
) : ViewModel() {

    private val prefs = repository.getPreferences()

    private val _serverUrl = MutableStateFlow(prefs.getServerUrl())
    val serverUrl: StateFlow<String> = _serverUrl.asStateFlow()

    private val _deviceName = MutableStateFlow(prefs.getDeviceName())
    val deviceName: StateFlow<String> = _deviceName.asStateFlow()

    private val _apiKey = MutableStateFlow(prefs.getApiKey() ?: "")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private val _deviceId = MutableStateFlow(prefs.getDeviceId())
    val deviceId: StateFlow<String> = _deviceId.asStateFlow()

    private val _userId = MutableStateFlow(prefs.getUserId())
    val userId: StateFlow<Int?> = _userId.asStateFlow()

    val isRegistered: StateFlow<Boolean> = _apiKey.map { it.isNotEmpty() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), prefs.getApiKey()?.isNotEmpty() ?: false)

    val isLocationEnabled = MutableStateFlow(false)

    private val _isRecording = MutableStateFlow(false)
    val isRecording: StateFlow<Boolean> = _isRecording.asStateFlow()

    private val _recordedFileUri = MutableStateFlow<String?>(null)
    val recordedFileUri: StateFlow<String?> = _recordedFileUri.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _isRefreshing = MutableStateFlow(false)
    val isRefreshing: StateFlow<Boolean> = _isRefreshing.asStateFlow()

    private val _testConnectionResult = MutableStateFlow<Result<Boolean>?>(null)
    val testConnectionResult: StateFlow<Result<Boolean>?> = _testConnectionResult.asStateFlow()

    private val _registrationResult = MutableStateFlow<Result<Boolean>?>(null)
    val registrationResult: StateFlow<Result<Boolean>?> = _registrationResult.asStateFlow()

    private val _loginResult = MutableStateFlow<Result<Boolean>?>(null)
    val loginResult: StateFlow<Result<Boolean>?> = _loginResult.asStateFlow()

    private val _uiEvent = MutableSharedFlow<String>()
    val uiEvent = _uiEvent.asSharedFlow()

    val messagesList: StateFlow<List<Message>> = repository.allMessages
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val inboxMessagesList: StateFlow<List<InboxMessageEntity>> = repository.allInboxMessages
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    // ---------- NEW SALES STATE ----------
    private val _products = MutableStateFlow<List<ProductResponse>>(emptyList())
    val products: StateFlow<List<ProductResponse>> = _products.asStateFlow()

    private val _customers = MutableStateFlow<List<CustomerResponse>>(emptyList())
    val customers: StateFlow<List<CustomerResponse>> = _customers.asStateFlow()

    private val _selectedCustomer = MutableStateFlow<CustomerResponse?>(null)
    val selectedCustomer: StateFlow<CustomerResponse?> = _selectedCustomer.asStateFlow()

    private val _cart = MutableStateFlow<List<OrderItemRequest>>(emptyList())
    val cart: StateFlow<List<OrderItemRequest>> = _cart.asStateFlow()

    private val _orderResult = MutableStateFlow<OrderPlaceResponse?>(null)
    val orderResult: StateFlow<OrderPlaceResponse?> = _orderResult.asStateFlow()

    private val _settings = MutableStateFlow<SettingsResponse?>(null)
    val settings: StateFlow<SettingsResponse?> = _settings.asStateFlow()

    private val _userRole = MutableStateFlow(prefs.getRole())
    val userRole: StateFlow<String?> = _userRole.asStateFlow()

    private val _cityId = MutableStateFlow(prefs.getCityId())
    val cityId: StateFlow<Int?> = _cityId.asStateFlow()

    private val _availableTokens = MutableStateFlow(prefs.getTokens())
    val availableTokens: StateFlow<List<String>> = _availableTokens.asStateFlow()

    private var mediaRecorder: MediaRecorder? = null
    private var currentRecordingFile: File? = null

    private var pollingJob: kotlinx.coroutines.Job? = null
    private var syncStatusJob: kotlinx.coroutines.Job? = null
    private var inboxPollingJob: kotlinx.coroutines.Job? = null
    private var productSyncJob: kotlinx.coroutines.Job? = null

    init {
        if (prefs.getApiKey()?.isNotEmpty() == true) {
            syncAndRefresh()
            syncProducts()
            loadSettings()
        }
        startInboxPolling()
        startPolling()
        startSyncStatusCheck()
        startProductSync()
    }

    fun loadSettings() {
        viewModelScope.launch {
            val fetched = repository.fetchSettings()
            if (fetched != null) {
                _settings.value = fetched
            }
        }
    }

    // ========== INBOX POLLING (existing) ==========
    fun startInboxPolling() {
        inboxPollingJob?.cancel()
        inboxPollingJob = viewModelScope.launch {
            while (true) {
                if (prefs.getApiKey()?.isNotEmpty() == true) {
                    val userId = prefs.getUserId()
                    if (userId != null && userId != -1) {
                        repository.fetchInbox(userId)
                    }
                }
                delay(30000)
            }
        }
    }

    fun markInboxMessageAsRead(id: Int) {
        viewModelScope.launch {
            repository.markInboxMessageAsRead(id)
        }
    }

    // ========== PRODUCT SYNC ==========
    private fun startProductSync() {
        productSyncJob?.cancel()
        productSyncJob = viewModelScope.launch {
            while (true) {
                delay(5 * 60 * 1000) // every 5 minutes
                if (prefs.getApiKey()?.isNotEmpty() == true) {
                    syncProducts()
                }
            }
        }
    }

    fun syncProducts() {
        viewModelScope.launch {
            val userId = prefs.getUserId() ?: return@launch
            val since = prefs.getLastProductSyncTimestamp()
            val cityId = prefs.getCityId()
            val result = repository.syncProducts(since, cityId)
            if (result != null) {
                val (newProducts, timestamp) = result
                // Merge with existing products
                val existing = _products.value.toMutableList()
                // Remove products that are no longer active
                val activeIds = newProducts.filter { it.is_active }.map { it.id }.toSet()
                existing.removeAll { !activeIds.contains(it.id) }
                // Update or add new products
                newProducts.forEach { newProduct ->
                    val index = existing.indexOfFirst { it.id == newProduct.id }
                    if (index != -1) {
                        existing[index] = newProduct
                    } else {
                        existing.add(newProduct)
                    }
                }
                _products.value = existing
                prefs.setLastProductSyncTimestamp(timestamp)
                _uiEvent.emit("Products synced: ${newProducts.size} changes")
            }
        }
    }

    // ========== LOCATION FIX ==========
    @SuppressLint("MissingPermission")
    suspend fun getCurrentLocation(): Pair<Double?, Double?>? {
        return try {
            val fusedLocationClient = LocationServices.getFusedLocationProviderClient(context)
            val locationResult = kotlinx.coroutines.suspendCancellableCoroutine<android.location.Location?> { continuation ->
                fusedLocationClient.lastLocation
                    .addOnSuccessListener { loc ->
                        continuation.resume(loc, onCancellation = null)
                    }
                    .addOnFailureListener {
                        continuation.resume(null, onCancellation = null)
                    }
            }
            if (locationResult != null) {
                return Pair(locationResult.latitude, locationResult.longitude)
            }
            
            // Fallback to network provider (offline)
            val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
            val networkLocation = locationManager.getLastKnownLocation(android.location.LocationManager.NETWORK_PROVIDER)
            if (networkLocation != null) {
                return Pair(networkLocation.latitude, networkLocation.longitude)
            }
            
            // Last resort: GPS
            val gpsLocation = locationManager.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)
            if (gpsLocation != null) {
                return Pair(gpsLocation.latitude, gpsLocation.longitude)
            }
            null
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }

    // ========== NEW: POLLING FOR NEW MESSAGES ==========
    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
            while (true) {
                val userId = prefs.getUserId()
                if (userId != null && userId != -1 && prefs.getApiKey()?.isNotEmpty() == true) {
                    val since = prefs.getLastPollTimestamp()
                    val newMessages = repository.pollNewMessages(userId, since)
                    if (newMessages != null && newMessages.isNotEmpty()) {
                        val existingIds = repository.messageDao.getAllServerIds().toSet()
                        val toInsert = newMessages.filter { it.serverId !in existingIds }
                        if (toInsert.isNotEmpty()) {
                            repository.messageDao.insertAll(toInsert)
                            val latest = newMessages.maxByOrNull { it.createdAt }
                            latest?.let {
                                val iso = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US)
                                    .format(java.util.Date(it.createdAt))
                                prefs.setLastPollTimestamp(iso)
                            }
                            _uiEvent.emit("New messages received: ${toInsert.size}")
                        }
                    }
                }
                delay(10000) // poll every 10 seconds
            }
        }
    }

    // ========== NEW: SYNC STATUS CHECK ==========
    private fun startSyncStatusCheck() {
        syncStatusJob?.cancel()
        syncStatusJob = viewModelScope.launch {
            while (true) {
                val userId = prefs.getUserId()
                if (userId != null && userId != -1 && prefs.getApiKey()?.isNotEmpty() == true) {
                    val status = repository.checkSyncStatus(userId)
                    if (status != null && status.uploadRequired) {
                        val result = repository.uploadAllMessages(userId)
                        if (result != null && result.success) {
                            _uiEvent.emit("Uploaded ${result.inserted} messages to server.")
                        } else {
                            _uiEvent.emit("Failed to upload all messages.")
                        }
                    }
                }
                delay(30000) // check every 30 seconds
            }
        }
    }

    fun saveServerUrl(url: String) {
        prefs.setServerUrl(url)
        _serverUrl.value = prefs.getServerUrl()
        repository.resetClient()
        viewModelScope.launch {
            _uiEvent.emit("Server URL updated successfully.")
        }
    }

    fun testConnection(url: String, apiKey: String) {
        viewModelScope.launch {
            _testConnectionResult.value = null
            _isLoading.value = true
            val backupUrl = prefs.getServerUrl()
            val backupKey = prefs.getApiKey()
            prefs.setServerUrl(url)
            prefs.setApiKey(apiKey)
            repository.resetClient()

            val success = repository.pingServer()
            
            prefs.setServerUrl(backupUrl)
            prefs.setApiKey(backupKey)
            repository.resetClient()
            _serverUrl.value = prefs.getServerUrl()
            _apiKey.value = prefs.getApiKey() ?: ""

            _isLoading.value = false
            _testConnectionResult.value = if (success) {
                Result.success(true)
            } else {
                Result.failure(Exception("Could not connect to $url"))
            }
        }
    }

    fun connectAndSave(url: String, apiKey: String) {
        viewModelScope.launch {
            _registrationResult.value = null
            _isLoading.value = true
            
            prefs.setServerUrl(url)
            prefs.setApiKey(apiKey)
            repository.resetClient()
            
            val success = repository.pingAndSaveUser()
            _isLoading.value = false
            
            _serverUrl.value = prefs.getServerUrl()
            _apiKey.value = prefs.getApiKey() ?: ""
            _deviceId.value = prefs.getDeviceId()
            _userId.value = prefs.getUserId()
            
            if (success) {
                _registrationResult.value = Result.success(true)
                _uiEvent.emit("Connected successfully! Server is online.")
                syncAndRefresh()
            } else {
                _registrationResult.value = Result.success(true)
                _uiEvent.emit("Connection failed, entered Offline Mode.")
                syncAndRefresh()
            }
        }
    }

    fun login(username: String, password: String, serverUrl: String, apiKey: String) {
        viewModelScope.launch {
            _loginResult.value = null
            _isLoading.value = true
            
            // Backup existing preferences in case validation fails
            val backupUrl = prefs.getServerUrl()
            val backupKey = prefs.getApiKey()
            val backupUserId = prefs.getUserId()
            val backupRole = prefs.getRole()
            val backupCityId = prefs.getCityId()
            val backupDeviceName = prefs.getDeviceName()

            // Temporarily set the inputs so the repository's client can construct the proper request
            prefs.setServerUrl(serverUrl)
            prefs.setApiKey(apiKey)
            repository.resetClient()
            
            val result = repository.login(username, password)
            _isLoading.value = false
            
            when (result) {
                is GyroPulseRepository.LoginResult.Success -> {
                    // Successful login! Keep the saved credentials and update local StateFlows
                    _serverUrl.value = prefs.getServerUrl()
                    _apiKey.value = prefs.getApiKey() ?: ""
                    _deviceId.value = prefs.getDeviceId()
                    _userId.value = prefs.getUserId()
                    _deviceName.value = prefs.getDeviceName()
                    _userRole.value = prefs.getRole()
                    _cityId.value = prefs.getCityId()
                    
                    _loginResult.value = Result.success(true)
                    _uiEvent.emit("Login successful! Welcome, $username.")
                    loadSettings()
                    syncAndRefresh()
                }
                is GyroPulseRepository.LoginResult.CityMissing -> {
                    _serverUrl.value = prefs.getServerUrl()
                    _apiKey.value = prefs.getApiKey() ?: ""
                    _deviceId.value = prefs.getDeviceId()
                    _userId.value = prefs.getUserId()
                    _deviceName.value = prefs.getDeviceName()
                    _userRole.value = prefs.getRole()
                    _cityId.value = null

                    _loginResult.value = Result.failure(Exception("Your account is not assigned to a city. Please contact admin."))
                    _uiEvent.emit("Login succeeded but city missing – some features disabled.")
                    loadSettings()
                    syncAndRefresh()
                }
                is GyroPulseRepository.LoginResult.InvalidCredentials -> {
                    // Revert to backup preferences
                    prefs.setServerUrl(backupUrl)
                    prefs.setApiKey(backupKey)
                    prefs.setUserId(backupUserId)
                    prefs.setRole(backupRole)
                    prefs.setCityId(backupCityId)
                    prefs.setDeviceName(backupDeviceName)
                    repository.resetClient()

                    _loginResult.value = Result.failure(Exception("Invalid username or password."))
                    _uiEvent.emit("Login failed: Invalid credentials.")
                }
                is GyroPulseRepository.LoginResult.ServerError -> {
                    // Revert to backup preferences
                    prefs.setServerUrl(backupUrl)
                    prefs.setApiKey(backupKey)
                    prefs.setUserId(backupUserId)
                    prefs.setRole(backupRole)
                    prefs.setCityId(backupCityId)
                    prefs.setDeviceName(backupDeviceName)
                    repository.resetClient()

                    _loginResult.value = Result.failure(Exception("Server error: ${result.message}"))
                    _uiEvent.emit("Login failed: Server error.")
                }
                is GyroPulseRepository.LoginResult.NetworkError -> {
                    // Revert to backup preferences
                    prefs.setServerUrl(backupUrl)
                    prefs.setApiKey(backupKey)
                    prefs.setUserId(backupUserId)
                    prefs.setRole(backupRole)
                    prefs.setCityId(backupCityId)
                    prefs.setDeviceName(backupDeviceName)
                    repository.resetClient()

                    _loginResult.value = Result.failure(Exception("Unable to connect to server. Please check base URL, API key, and network connectivity."))
                    _uiEvent.emit("Login failed: Connection error.")
                }
            }
        }
    }

    fun clearAllData() {
        viewModelScope.launch {
            prefs.clear()
            _apiKey.value = ""
            _userId.value = null
            _deviceName.value = prefs.getDeviceName()
            _deviceId.value = prefs.getDeviceId()
            _userRole.value = null
            _cityId.value = null
            _registrationResult.value = null
            _testConnectionResult.value = null
            _loginResult.value = null
            repository.resetClient()
            _uiEvent.emit("Credentials cleared successfully.")
        }
    }

    fun handleSelectedMedia(uri: Uri, extension: String) {
        val savedPath = repository.saveFileToInternalStorage(uri, extension)
        if (savedPath != null) {
            _recordedFileUri.value = savedPath
            viewModelScope.launch {
                _uiEvent.emit("Attachment added successfully!")
            }
        } else {
            viewModelScope.launch {
                _uiEvent.emit("Failed to save attachment.")
            }
        }
    }

    fun clearSelectedMedia() {
        _recordedFileUri.value = null
    }

    fun startRecording() {
        try {
            _recordedFileUri.value = null
            currentRecordingFile = repository.createLocalFileForRecording("m4a")
            
            val recorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(context)
            } else {
                @Suppress("DEPRECATION")
                MediaRecorder()
            }

            recorder.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setOutputFile(currentRecordingFile!!.absolutePath)
                prepare()
                start()
            }
            mediaRecorder = recorder
            _isRecording.value = true
        } catch (e: Exception) {
            e.printStackTrace()
            _isRecording.value = false
            currentRecordingFile = null
            viewModelScope.launch {
                _uiEvent.emit("Could not start recording: ${e.localizedMessage}")
            }
        }
    }

    fun stopRecording() {
        if (!_isRecording.value) return
        try {
            mediaRecorder?.apply {
                stop()
                release()
            }
            mediaRecorder = null
            _isRecording.value = false
            
            if (currentRecordingFile != null && currentRecordingFile!!.exists()) {
                val maxSize = 9 * 1024 * 1024
                if (currentRecordingFile!!.length() > maxSize) {
                    currentRecordingFile!!.delete()
                    _recordedFileUri.value = null
                    viewModelScope.launch {
                        _uiEvent.emit("Voice recording discarded: size exceeds 9 MB limit.")
                    }
                } else {
                    _recordedFileUri.value = currentRecordingFile!!.absolutePath
                    viewModelScope.launch {
                        _uiEvent.emit("Voice memo saved successfully!")
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
            _isRecording.value = false
            viewModelScope.launch {
                _uiEvent.emit("Error stopping recording: ${e.localizedMessage}")
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun sendNewMessage(type: String, content: String?) {
        viewModelScope.launch {
            _isLoading.value = true
            var latitude: Double? = null
            var longitude: Double? = null

            if (isLocationEnabled.value) {
                val location = getCurrentLocation()
                latitude = location?.first
                longitude = location?.second
            }

            val attachmentPath = _recordedFileUri.value
            
            val insertId = repository.insertLocalMessage(
                type = type,
                content = content,
                mediaUri = attachmentPath,
                latitude = latitude,
                longitude = longitude
            )

            _recordedFileUri.value = null
            _isLoading.value = false

            _uiEvent.emit("Saved locally. Uploading to server...")
            
            viewModelScope.launch {
                val uploadSuccess = repository.uploadMessageImmediately(insertId)
                if (uploadSuccess) {
                    _uiEvent.emit("Message successfully uploaded and synced!")
                } else {
                    _uiEvent.emit("Network offline. Message will auto-sync once connection is restored.")
                }
            }
        }
    }

    fun syncAndRefresh() {
        viewModelScope.launch {
            _isRefreshing.value = true
            
            val syncSuccess = repository.performBatchSync()
            val fetchSuccess = repository.fetchAdminReplies()
            val userId = prefs.getUserId() ?: 1
            val inboxSuccess = repository.fetchInbox(userId)

            _isRefreshing.value = false

            if (syncSuccess && fetchSuccess && inboxSuccess) {
                _uiEvent.emit("Sync complete. Activity and inbox up to date.")
            } else {
                _uiEvent.emit("Sync completed with warnings. Device may be offline.")
            }
        }
    }

    private var activePlayer: android.media.MediaPlayer? = null
    private val _currentlyPlayingId = MutableStateFlow<Long?>(null)
    val currentlyPlayingId = _currentlyPlayingId.asStateFlow()

    fun playVoice(messageId: Long, filePath: String) {
        viewModelScope.launch {
            if (_currentlyPlayingId.value == messageId) {
                stopPlayingVoice()
                return@launch
            }
            
            stopPlayingVoice()
            
            try {
                val player = android.media.MediaPlayer().apply {
                    setDataSource(filePath)
                    prepareAsync()
                    setOnPreparedListener {
                        start()
                    }
                    setOnCompletionListener {
                        stopPlayingVoice()
                    }
                    setOnErrorListener { _, _, _ ->
                        stopPlayingVoice()
                        true
                    }
                }
                activePlayer = player
                _currentlyPlayingId.value = messageId
            } catch (e: Exception) {
                e.printStackTrace()
                _uiEvent.emit("Cannot play audio: ${e.message}")
                stopPlayingVoice()
            }
        }
    }

    fun stopPlayingVoice() {
        try {
            activePlayer?.apply {
                if (isPlaying) {
                    stop()
                }
                release()
            }
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            activePlayer = null
            _currentlyPlayingId.value = null
        }
    }

    fun exportBackup(context: Context, targetUri: Uri) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                val sharedPrefs = context.getSharedPreferences("gyropulse_prefs", Context.MODE_PRIVATE)
                val backupUri = BackupManager.exportBackup(context, sharedPrefs)
                context.contentResolver.openOutputStream(targetUri)?.use { output ->
                    context.contentResolver.openInputStream(backupUri)?.use { input ->
                        input.copyTo(output)
                    }
                }
                _uiEvent.emit("Backup exported successfully!")
            } catch (e: Exception) {
                e.printStackTrace()
                _uiEvent.emit("Export failed: ${e.message}")
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun importBackup(context: Context, zipUri: Uri) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                val success = BackupManager.importBackup(context, zipUri)
                if (success) {
                    _serverUrl.value = prefs.getServerUrl()
                    _apiKey.value = prefs.getApiKey() ?: ""
                    _deviceName.value = prefs.getDeviceName()
                    _deviceId.value = prefs.getDeviceId()
                    _userId.value = prefs.getUserId()
                    _userRole.value = prefs.getRole()
                    _cityId.value = prefs.getCityId()
                    repository.resetClient()
                    _uiEvent.emit("Backup imported successfully!")
                    syncAndRefresh()
                } else {
                    _uiEvent.emit("Import failed. Please check the backup file.")
                }
            } catch (e: Exception) {
                e.printStackTrace()
                _uiEvent.emit("Import error: ${e.message}")
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun downloadHistoricalData(from: String?, to: String?, type: String?) {
        viewModelScope.launch {
            _isLoading.value = true
            val userId = prefs.getUserId() ?: -1
            if (userId == -1) {
                _uiEvent.emit("User ID not available. Please log in again.")
                _isLoading.value = false
                return@launch
            }
            try {
                val messages = repository.fetchHistoricalMessages(userId, from, to, type)
                if (messages == null || messages.isEmpty()) {
                    _uiEvent.emit("No messages found for the selected filters.")
                    _isLoading.value = false
                    return@launch
                }
                val inserted = repository.importHistoricalMessages(messages)
                _uiEvent.emit("Successfully imported $inserted messages from server.")
            } catch (e: Exception) {
                _uiEvent.emit("Error: ${e.message}")
            } finally {
                _isLoading.value = false
            }
        }
    }

    // ---------- NEW SALES METHODS ----------
    fun searchProducts(query: String, barcode: String? = null) {
        viewModelScope.launch {
            _isLoading.value = true
            val results = repository.searchProducts(query, barcode)
            results?.let { _products.value = it }
            _isLoading.value = false
        }
    }

    fun searchCustomers(query: String) {
        viewModelScope.launch {
            _isLoading.value = true
            val results = repository.searchCustomers(query)
            results?.let { _customers.value = it }
            _isLoading.value = false
        }
    }

    fun selectCustomer(customer: CustomerResponse?) {
        _selectedCustomer.value = customer
    }

    fun createCustomer(name: String, phone: String, address: String?) {
        viewModelScope.launch {
            _isLoading.value = true
            val customer = repository.createCustomer(name, phone, address)
            customer?.let {
                _selectedCustomer.value = it
                _uiEvent.emit("Customer created: ${it.name}")
            } ?: run {
                _uiEvent.emit("Failed to create customer")
            }
            _isLoading.value = false
        }
    }

    fun addToCart(product: ProductResponse, qty: Int) {
        val existing = _cart.value.find { it.product_id == product.id }
        val newList = _cart.value.toMutableList()
        if (existing != null) {
            val index = newList.indexOf(existing)
            newList[index] = existing.copy(qty = existing.qty + qty)
        } else {
            newList.add(
                OrderItemRequest(
                    product_id = product.id,
                    qty = qty,
                    unit_price = product.unit_price,
                    note = null
                )
            )
        }
        _cart.value = newList
        viewModelScope.launch {
            _uiEvent.emit("Added ${product.name} to cart")
        }
    }

    fun removeFromCart(productId: Int) {
        _cart.value = _cart.value.filter { it.product_id != productId }
    }

    fun clearCart() {
        _cart.value = emptyList()
    }

    fun placeOrder(
        customerId: Int?,
        customerName: String,
        customerPhone: String,
        shippingAddress: String?,
        latitude: Double?,
        longitude: Double?,
        paidAmount: Double,
        paymentTerms: String?,
        specialInstructions: String?,
        files: List<File>? = null
    ) {
        viewModelScope.launch {
            _isLoading.value = true
            val items = _cart.value
            if (items.isEmpty()) {
                _uiEvent.emit("Cart is empty")
                _isLoading.value = false
                return@launch
            }

            var finalLat = latitude
            var finalLon = longitude
            if (isLocationEnabled.value && (finalLat == null || finalLon == null)) {
                val loc = getCurrentLocation()
                finalLat = loc?.first
                finalLon = loc?.second
            }

            // 1️⃣ If customerId is null, create a new customer first
            var finalCustomerId = customerId
            if (finalCustomerId == null && customerName.isNotBlank() && customerPhone.isNotBlank()) {
                val newCustomer = repository.createCustomer(customerName, customerPhone, shippingAddress)
                if (newCustomer != null) {
                    finalCustomerId = newCustomer.id
                    _selectedCustomer.value = newCustomer
                    _uiEvent.emit("Customer created: ${newCustomer.name}")
                } else {
                    _uiEvent.emit("Failed to create customer. Please check your connection.")
                    _isLoading.value = false
                    return@launch
                }
            }

            if (finalCustomerId == null) {
                _uiEvent.emit("Please provide customer details or select an existing customer.")
                _isLoading.value = false
                return@launch
            }

            // 2️⃣ Calculate totals
            val subtotal = items.sumOf { it.unit_price * it.qty }
            val taxRate = (_settings.value?.tax_rate ?: 5.0) / 100.0
            val tax = subtotal * taxRate
            val discount = 0.0
            val netTotal = subtotal + tax - discount

            // 3️⃣ Place the order with the (new or existing) customer ID
            val result = repository.placeOrder(
                customerId = finalCustomerId,
                customerName = customerName,
                customerPhone = customerPhone,
                shippingAddress = shippingAddress,
                latitude = finalLat,
                longitude = finalLon,
                items = items,
                subtotal = subtotal,
                taxAmount = tax,
                discount = discount,
                netTotal = netTotal,
                paidAmount = paidAmount,
                paymentTerms = paymentTerms,
                specialInstructions = specialInstructions,
                files = null
            )

            if (result != null && result.status in listOf("success", "queued")) {
                _orderResult.value = result
                _uiEvent.emit(if (result.status == "queued") "Order saved offline; awaiting server confirmation" else "Order #${result.order_id} placed successfully!")
                clearCart()
                _selectedCustomer.value = null
            } else {
                _uiEvent.emit("Order failed: ${result?.message ?: "Unknown error"}")
            }
            _isLoading.value = false
        }
    }

    fun resetOrderResult() {
        _orderResult.value = null
    }

    /**
     * Import and activate device via .gpc file Uri.
     */
    fun importGpcFile(uri: Uri) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    ?: throw Exception("Could not open GPC file stream")

                val configuredMasterSecret = ConfigManager.getConfig(context, ConfigManager.Keys.MASTER_SECRET) ?: GpcCryptoService.DEFAULT_MASTER_SECRET
                val payload = GpcCryptoService.decryptPayload(bytes, configuredMasterSecret)

                val userId = payload.optInt("user_id", -1)
                val username = payload.optString("username", "")
                val apiKey = payload.optString("api_key", "")
                val deviceUuid = payload.optString("device_uuid", "")
                val role = payload.optString("role", "sales_rep")
                val cityId = payload.optInt("city_id", -1)
                val serverUrl = if (payload.has("base_url")) payload.optString("base_url") else payload.optString("server_url", "")
                val sessionId = payload.optString("session_id", "")
                val newMasterSecret = payload.optString("master_secret", "")

                if (apiKey.isEmpty() && !payload.has("api_key")) {
                    throw Exception("Invalid GPC: Missing API key")
                }

                if (newMasterSecret.isNotEmpty()) {
                    ConfigManager.setConfig(context, ConfigManager.Keys.MASTER_SECRET, newMasterSecret)
                }

                if (serverUrl.isNotEmpty()) {
                    prefs.setServerUrl(serverUrl)
                }
                if (apiKey.isNotEmpty()) {
                    prefs.setApiKey(apiKey)
                }
                if (userId != -1) {
                    prefs.setUserId(userId)
                }
                if (username.isNotEmpty()) {
                    prefs.setDeviceName(username)
                }
                if (deviceUuid.isNotEmpty()) {
                    context.getSharedPreferences("gyropulse_prefs", Context.MODE_PRIVATE)
                        .edit().putString("device_id", deviceUuid).apply()
                    _deviceId.value = deviceUuid
                }
                if (role.isNotEmpty()) {
                    prefs.setRole(role)
                }
                if (cityId != -1) {
                    prefs.setCityId(cityId)
                }
                if (sessionId.isNotEmpty()) {
                    prefs.setSessionId(sessionId)
                }

                if (payload.has("tokens")) {
                    val tokensArr = payload.getJSONArray("tokens")
                    val list = mutableListOf<String>()
                    for (i in 0 until tokensArr.length()) {
                        list.add(tokensArr.getString(i))
                    }
                    prefs.setTokens(list)
                }

                prefs.syncToEnvConfig()
                repository.resetClient()

                _serverUrl.value = prefs.getServerUrl()
                _apiKey.value = prefs.getApiKey() ?: ""
                _deviceId.value = prefs.getDeviceId()
                _userId.value = prefs.getUserId()
                _deviceName.value = prefs.getDeviceName()
                _userRole.value = prefs.getRole()
                _cityId.value = prefs.getCityId()
                _availableTokens.value = prefs.getTokens()

                _loginResult.value = Result.success(true)
                val welcomeName = if (username.isNotEmpty()) username else "User"
                _uiEvent.emit("Welcome $welcomeName! Activated via GPC file.")
                syncAndRefresh()
            } catch (e: Exception) {
                Log.e("GyroPulseViewModel", "Failed to import GPC file", e)
                _loginResult.value = Result.failure(e)
                _uiEvent.emit("GPC Import Error: ${e.localizedMessage ?: "Invalid file"}")
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Mobile LAN sync: pulls latest catalog, refills tokens, and processes server commands.
     */
    fun syncMobile() {
        viewModelScope.launch {
            _isRefreshing.value = true
            try {
                val syncResult = repository.syncMobile()
                _availableTokens.value = prefs.getTokens()
                syncProducts()
                syncAndRefresh()
                if (syncResult != null) {
                    val tokensCount = _availableTokens.value.size
                    _uiEvent.emit("Sync successful! Available tokens: $tokensCount")
                } else {
                    _uiEvent.emit("Sync completed locally.")
                }
            } catch (e: Exception) {
                Log.e("GyroPulseViewModel", "Error during mobile sync", e)
                _uiEvent.emit("Sync Error: ${e.localizedMessage ?: "Network error"}")
            } finally {
                _isRefreshing.value = false
            }
        }
    }

    /**
     * Export pending orders and messages as an encrypted GPC file.
     */
    suspend fun exportOrdersGpc(): Uri? {
        return try {
            val user = prefs.getDeviceName()
            val userId = prefs.getUserId() ?: 1
            val apiKey = prefs.getApiKey() ?: ""
            val deviceUuid = prefs.getDeviceId()
            val sessionId = prefs.getSessionId() ?: ""

            val tokens = prefs.getTokens()
            if (tokens.isEmpty()) {
                _uiEvent.emit("No tokens available. Please sync on LAN to refill.")
                return null
            }

            val token = prefs.useToken() ?: tokens.first()
            _availableTokens.value = prefs.getTokens()

            // Fetch pending local messages and orders
            val pendingMessages = repository.messageDao.getPendingMessages()
            val ordersArray = JSONArray()
            val mediaArray = JSONArray()

            for (msg in pendingMessages) {
                val orderObj = JSONObject().apply {
                    put("id", msg.id)
                    put("type", msg.type)
                    put("content", msg.content ?: "")
                    put("latitude", msg.latitude)
                    put("longitude", msg.longitude)
                    put("created_at", msg.createdAt)
                    put("status", "pending")
                }
                ordersArray.put(orderObj)

                if (!msg.mediaUri.isNullOrEmpty()) {
                    val mediaObj = JSONObject().apply {
                        put("message_id", msg.id)
                        put("file_path", msg.mediaUri)
                        put("type", msg.type)
                    }
                    mediaArray.put(mediaObj)
                }
            }

            val payload = JSONObject().apply {
                put("user_id", userId)
                put("username", user)
                put("api_key", apiKey)
                put("device_uuid", deviceUuid)
                put("session_id", sessionId)
                put("token", token)
                put("orders", ordersArray)
                put("media", mediaArray)
                put("export_timestamp", java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US).format(java.util.Date()))
            }

            val masterSecret = ConfigManager.getConfig(context, ConfigManager.Keys.MASTER_SECRET)
                ?: GpcCryptoService.DEFAULT_MASTER_SECRET
            val encryptedBase64 = GpcCryptoService.encryptPayload(payload, masterSecret)
            val fileName = "Export_${user.replace(" ", "_")}_${System.currentTimeMillis()}.gpc"
            val file = File(context.cacheDir, fileName)
            file.writeText(encryptedBase64)

            // Mark local records as exported/synced
            for (msg in pendingMessages) {
                repository.messageDao.updateSyncStatus(msg.id, true, null)
            }

            FileProvider.getUriForFile(context, "com.example.fileprovider", file)
        } catch (e: Exception) {
            Log.e("GyroPulseViewModel", "Error exporting orders to GPC", e)
            _uiEvent.emit("Export failed: ${e.localizedMessage}")
            null
        }
    }

    fun logout() {
        prefs.clear()
        _apiKey.value = ""
        _userId.value = null
        _userRole.value = null
        _cityId.value = null
        _cart.value = emptyList()
        _selectedCustomer.value = null
        _orderResult.value = null
        repository.resetClient()
        viewModelScope.launch {
            _uiEvent.emit("Logged out successfully.")
        }
    }

    override fun onCleared() {
        super.onCleared()
        pollingJob?.cancel()
        syncStatusJob?.cancel()
        inboxPollingJob?.cancel()
        try {
            mediaRecorder?.release()
        } catch (_: Exception) {}
        try {
            stopPlayingVoice()
        } catch (_: Exception) {}
    }
}

class GyroPulseViewModelFactory(
    private val context: Context
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(GyroPulseViewModel::class.java)) {
            val db = AppDatabase.getDatabase(context)
            val prefs = GyroPulsePreferences(context)
            val repository = GyroPulseRepository(context, db.messageDao(), db.inboxMessageDao(), prefs)
            return GyroPulseViewModel(context, repository) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class")
    }
}
