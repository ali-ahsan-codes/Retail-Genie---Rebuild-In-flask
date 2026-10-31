package com.example

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.work.*
import com.example.sync.SyncWorker
import com.example.ui.viewmodel.GyroPulseViewModel
import com.example.ui.viewmodel.GyroPulseViewModelFactory
import com.example.ui.screens.GyroPulseApp
import com.example.ui.screens.SettingsScreen
import com.example.ui.screens.LoginScreen
import com.example.ui.screens.SalesDashboardScreen
import com.example.ui.screens.CartScreen
import com.example.ui.screens.OrderFormScreen
import com.example.ui.screens.ExportScreen
import com.example.ui.theme.MyApplicationTheme
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {

    private val viewModel: GyroPulseViewModel by viewModels { GyroPulseViewModelFactory(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Handle opening of .gpc file on launch
        handleIncomingIntent(intent)

        // Schedule periodic background synchronization worker
        setupBackgroundSync()

        setContent {
            MyApplicationTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val isRegistered by viewModel.isRegistered.collectAsState()
                    var currentScreen by remember { mutableStateOf(if (isRegistered) "sales_dashboard" else "login") }

                    // Enforce setup screen if the device is not registered yet
                    LaunchedEffect(isRegistered) {
                        currentScreen = if (isRegistered) "sales_dashboard" else "login"
                    }

                    when (currentScreen) {
                        "sales_dashboard" -> {
                            SalesDashboardScreen(
                                viewModel = viewModel,
                                onLogout = { viewModel.logout() },
                                onNewOrder = { currentScreen = "order_form" },
                                onViewCart = { currentScreen = "cart" },
                                onSettings = { currentScreen = "settings" },
                                onMessages = { currentScreen = "messages" },
                                onExport = { currentScreen = "export" }
                            )
                        }
                        "export" -> {
                            ExportScreen(
                                viewModel = viewModel,
                                onBack = { currentScreen = "sales_dashboard" }
                            )
                        }
                        "messages" -> {
                            GyroPulseApp(
                                viewModel = viewModel,
                                onNavigateToSettings = { currentScreen = "settings" },
                                onBackToSalesDashboard = { currentScreen = "sales_dashboard" }
                            )
                        }
                        "login" -> {
                            LoginScreen(
                                viewModel = viewModel,
                                onNavigateToSettings = { currentScreen = "settings" }
                            )
                        }
                        "settings" -> {
                            SettingsScreen(
                                viewModel = viewModel,
                                onBackToDashboard = { currentScreen = if (isRegistered) "sales_dashboard" else "login" },
                                showBackButton = true
                            )
                        }
                        "cart" -> {
                            CartScreen(
                                viewModel = viewModel,
                                onBack = { currentScreen = "sales_dashboard" },
                                onCheckout = { currentScreen = "order_form" }
                            )
                        }
                        "order_form" -> {
                            OrderFormScreen(
                                viewModel = viewModel,
                                onBack = { currentScreen = "sales_dashboard" },
                                onOrderPlaced = { currentScreen = "sales_dashboard" }
                            )
                        }
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        if (intent == null) return
        val uri: Uri? = intent.data ?: intent.clipData?.getItemAt(0)?.uri
        if (uri != null) {
            val scheme = uri.scheme
            val path = uri.path?.lowercase() ?: ""
            if (scheme == "content" || scheme == "file" || path.endsWith(".gpc")) {
                viewModel.importGpcFile(uri)
            }
        }
    }

    private fun setupBackgroundSync() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

        val syncRequest = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .build()

        WorkManager.getInstance(applicationContext).enqueueUniquePeriodicWork(
            "GyroPulseBackgroundSync",
            ExistingPeriodicWorkPolicy.KEEP,
            syncRequest
        )
    }
}
