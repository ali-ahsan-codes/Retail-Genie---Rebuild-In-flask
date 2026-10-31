package com.example.ui.screens

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.ui.theme.grainBackground
import com.example.ui.scanner.BarcodeScannerView
import com.example.ui.viewmodel.GyroPulseViewModel
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrderFormScreen(
    viewModel: GyroPulseViewModel,
    onBack: () -> Unit,
    onOrderPlaced: () -> Unit
) {
    val context = LocalContext.current
    val isLoading by viewModel.isLoading.collectAsStateWithLifecycle()
    val selectedCustomer by viewModel.selectedCustomer.collectAsStateWithLifecycle()
    val cart by viewModel.cart.collectAsStateWithLifecycle()
    val products by viewModel.products.collectAsStateWithLifecycle()
    val customers by viewModel.customers.collectAsStateWithLifecycle()
    val orderResult by viewModel.orderResult.collectAsStateWithLifecycle()
    val settings by viewModel.settings.collectAsStateWithLifecycle()
    val currency = settings?.currency ?: "$"

    // Manual entry fields
    var manualName by remember { mutableStateOf("") }
    var manualPhone by remember { mutableStateOf("") }
    var manualAddress by remember { mutableStateOf("") }

    // Whether to use manual entry or search
    var useManualEntry by remember { mutableStateOf(false) }

    var location by remember { mutableStateOf<Pair<Double?, Double?>>(null to null) }

    LaunchedEffect(Unit) {
        val loc = viewModel.getCurrentLocation()
        if (loc != null) {
            location = loc
        }
    }

    var customerSearch by remember { mutableStateOf("") }
    var productSearch by remember { mutableStateOf("") }
    var shippingAddress by remember { mutableStateOf("") }
    var paidAmount by remember { mutableStateOf("0.0") }
    var paymentTerms by remember { mutableStateOf("Cash on Delivery") }
    var specialInstructions by remember { mutableStateOf("") }
    var selectedFiles by remember { mutableStateOf<List<File>>(emptyList()) }

    var showCameraScanner by remember { mutableStateOf(false) }
    var showCreateCustomerDialog by remember { mutableStateOf(false) }

    // State for creating a new customer
    var newCustomerName by remember { mutableStateOf("") }
    var newCustomerPhone by remember { mutableStateOf("") }
    var newCustomerAddress by remember { mutableStateOf("") }

    val filePickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetMultipleContents()
    ) { uris: List<Uri> ->
        val files = uris.mapNotNull { uri ->
            val file = File(context.cacheDir, "temp_${System.currentTimeMillis()}")
            context.contentResolver.openInputStream(uri)?.use { input ->
                file.outputStream().use { output -> input.copyTo(output) }
                file
            }
        }
        selectedFiles = selectedFiles + files
    }

    // Observe order result to navigate back
    LaunchedEffect(orderResult) {
        if (orderResult != null) {
            viewModel.resetOrderResult()
            onOrderPlaced()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("New Order", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.clearCart() }) {
                        Icon(Icons.Default.DeleteSweep, contentDescription = "Clear Cart")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                )
            )
        }
    ) { innerPadding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .background(MaterialTheme.colorScheme.background)
                .grainBackground()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Camera scanner overlay
            item {
                AnimatedVisibility(visible = showCameraScanner) {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(280.dp),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                    ) {
                        Box(modifier = Modifier.fillMaxSize()) {
                            BarcodeScannerView(
                                onBarcodeScanned = { barcode ->
                                    showCameraScanner = false
                                    productSearch = barcode
                                    viewModel.searchProducts("", barcode)
                                }
                            )
                            IconButton(
                                onClick = { showCameraScanner = false },
                                modifier = Modifier
                                    .align(Alignment.TopEnd)
                                    .padding(8.dp)
                                    .background(Color.Black.copy(alpha = 0.5f), shape = RoundedCornerShape(20.dp))
                            ) {
                                Icon(Icons.Default.Close, contentDescription = "Close Camera", tint = Color.White)
                            }
                        }
                    }
                }
            }

            // 1. Customer Information - now supports both search and manual entry
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("Customer Information", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            // Toggle between search and manual
                            TextButton(onClick = { useManualEntry = !useManualEntry }) {
                                Icon(
                                    if (useManualEntry) Icons.Default.Search else Icons.Default.Edit,
                                    contentDescription = if (useManualEntry) "Search" else "Manual Entry"
                                )
                                Spacer(modifier = Modifier.width(4.dp))
                                Text(if (useManualEntry) "Search Customer" else "Enter Manually")
                            }
                        }

                        if (useManualEntry) {
                            // Manual entry fields
                            OutlinedTextField(
                                value = manualName,
                                onValueChange = { manualName = it },
                                label = { Text("Customer Name *") },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(12.dp)
                            )
                            OutlinedTextField(
                                value = manualPhone,
                                onValueChange = { manualPhone = it },
                                label = { Text("Customer Phone *") },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(12.dp)
                            )
                            OutlinedTextField(
                                value = manualAddress,
                                onValueChange = { manualAddress = it },
                                label = { Text("Shipping Address") },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(12.dp)
                            )
                            // Auto-fill shipping address from manual address
                            LaunchedEffect(manualAddress) {
                                if (shippingAddress.isEmpty()) {
                                    shippingAddress = manualAddress
                                }
                            }
                        } else {
                            // Search / Select existing customer
                            if (selectedCustomer != null) {
                                ListItem(
                                    headlineContent = { Text(selectedCustomer!!.name, fontWeight = FontWeight.Bold) },
                                    supportingContent = { Text("Phone: ${selectedCustomer!!.phone}\nAddress: ${selectedCustomer!!.shipping_address ?: "Not provided"}") },
                                    leadingContent = {
                                        Box(
                                            modifier = Modifier
                                                .size(40.dp)
                                                .background(MaterialTheme.colorScheme.secondaryContainer, shape = RoundedCornerShape(20.dp)),
                                            contentAlignment = Alignment.Center
                                        ) {
                                            Icon(Icons.Default.Person, contentDescription = null, tint = MaterialTheme.colorScheme.onSecondaryContainer)
                                        }
                                    },
                                    trailingContent = {
                                        IconButton(onClick = { viewModel.selectCustomer(null) }) {
                                            Icon(Icons.Default.Edit, contentDescription = "Change Customer", tint = MaterialTheme.colorScheme.primary)
                                        }
                                    },
                                    colors = ListItemDefaults.colors(containerColor = Color.Transparent)
                                )
                                // Auto-populate shipping address if customer is selected
                                LaunchedEffect(selectedCustomer) {
                                    selectedCustomer?.shipping_address?.let {
                                        if (shippingAddress.isEmpty()) {
                                            shippingAddress = it
                                        }
                                    }
                                }
                            } else {
                                OutlinedTextField(
                                    value = customerSearch,
                                    onValueChange = {
                                        customerSearch = it
                                        viewModel.searchCustomers(it)
                                    },
                                    label = { Text("Search Customer") },
                                    placeholder = { Text("Type customer name or phone") },
                                    leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                                    modifier = Modifier.fillMaxWidth(),
                                    shape = RoundedCornerShape(12.dp)
                                )

                                if (customers.isNotEmpty() && customerSearch.isNotEmpty()) {
                                    Surface(
                                        modifier = Modifier.fillMaxWidth(),
                                        shape = RoundedCornerShape(12.dp),
                                        tonalElevation = 2.dp,
                                        border = CardDefaults.outlinedCardBorder()
                                    ) {
                                        Column {
                                            customers.take(5).forEach { customer ->
                                                DropdownMenuItem(
                                                    text = { Text("${customer.name} (${customer.phone})") },
                                                    onClick = {
                                                        viewModel.selectCustomer(customer)
                                                        customerSearch = ""
                                                    }
                                                )
                                            }
                                            // Add an option to create new customer if not found
                                            DropdownMenuItem(
                                                text = { Text("+ Add New Customer", color = MaterialTheme.colorScheme.primary) },
                                                onClick = {
                                                    showCreateCustomerDialog = true
                                                    customerSearch = ""
                                                }
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 2. Product Catalog Selection
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Add Products to Cart", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            OutlinedTextField(
                                value = productSearch,
                                onValueChange = {
                                    productSearch = it
                                    viewModel.searchProducts(it)
                                },
                                label = { Text("Search Products") },
                                placeholder = { Text("Search by name or barcode") },
                                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(12.dp),
                                singleLine = true
                            )
                            IconButton(
                                onClick = { showCameraScanner = true },
                                modifier = Modifier
                                    .size(54.dp)
                                    .background(MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(12.dp))
                            ) {
                                Icon(Icons.Default.QrCodeScanner, contentDescription = "Scan Barcode", tint = MaterialTheme.colorScheme.onPrimaryContainer)
                            }
                        }

                        if (products.isNotEmpty()) {
                            Surface(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(12.dp),
                                tonalElevation = 1.dp,
                                border = CardDefaults.outlinedCardBorder()
                            ) {
                                Column(modifier = Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    products.take(4).forEach { product ->
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .padding(vertical = 4.dp),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Column(modifier = Modifier.weight(1f)) {
                                                Text(product.name, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                                Text("Price: ${currency}${product.unit_price} | Stock: ${product.current_warehouse_qty}", style = MaterialTheme.typography.bodySmall)
                                            }
                                            Button(
                                                onClick = {
                                                    viewModel.addToCart(product, 1)
                                                    productSearch = ""
                                                },
                                                shape = RoundedCornerShape(8.dp),
                                                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 4.dp),
                                                modifier = Modifier.height(32.dp)
                                            ) {
                                                Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(14.dp))
                                                Spacer(modifier = Modifier.width(2.dp))
                                                Text("Add", fontSize = 12.sp)
                                            }
                                        }
                                        HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 3. Cart Summary List
            if (cart.isNotEmpty()) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                    ) {
                        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Current Order Items (${cart.size})", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            
                            cart.forEach { item ->
                                val productObj = products.find { it.id == item.product_id }
                                val name = productObj?.name ?: "Product #${item.product_id}"
                                val price = item.unit_price

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column {
                                        Text(name, fontWeight = FontWeight.Medium)
                                        Text("${item.qty} units @ ${currency}${price}", style = MaterialTheme.typography.bodySmall)
                                    }
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text("${currency}${String.format("%.2f", price * item.qty)}", fontWeight = FontWeight.Bold)
                                        IconButton(onClick = { viewModel.removeFromCart(item.product_id) }) {
                                            Icon(Icons.Default.Delete, contentDescription = null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                                        }
                                    }
                                }
                            }
                            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                            val subtotal = cart.sumOf { it.unit_price * it.qty }
                            val taxRate = (settings?.tax_rate ?: 5.0) / 100.0
                            val taxLabel = settings?.tax_label ?: "Tax"
                            val taxAmount = subtotal * taxRate
                            val totalAmount = subtotal + taxAmount

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Subtotal", fontWeight = FontWeight.Medium)
                                Text("${currency}${String.format("%.2f", subtotal)}", fontWeight = FontWeight.Bold)
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("$taxLabel (${String.format("%.1f", taxRate * 100)}%)", fontWeight = FontWeight.Medium)
                                Text("${currency}${String.format("%.2f", taxAmount)}", fontWeight = FontWeight.Bold)
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Total", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                                Text("${currency}${String.format("%.2f", totalAmount)}", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
            }

            // 4. Order Billing and Delivery Details
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Billing & Logistics", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                        OutlinedTextField(
                            value = shippingAddress,
                            onValueChange = { shippingAddress = it },
                            label = { Text("Delivery Shipping Address") },
                            leadingIcon = { Icon(Icons.Default.LocalShipping, contentDescription = null) },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp)
                        )

                        OutlinedTextField(
                            value = paidAmount,
                            onValueChange = { paidAmount = it },
                            label = { Text("Paid Upfront Amount") },
                            leadingIcon = { Icon(Icons.Default.AttachMoney, contentDescription = null) },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp)
                        )

                        OutlinedTextField(
                            value = paymentTerms,
                            onValueChange = { paymentTerms = it },
                            label = { Text("Payment Terms") },
                            placeholder = { Text("e.g. Cash on Delivery, Net 30, Cash") },
                            leadingIcon = { Icon(Icons.Default.CreditCard, contentDescription = null) },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp)
                        )

                        OutlinedTextField(
                            value = specialInstructions,
                            onValueChange = { specialInstructions = it },
                            label = { Text("Special Instructions") },
                            placeholder = { Text("Delivery details or order comments") },
                            leadingIcon = { Icon(Icons.Default.Note, contentDescription = null) },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp)
                        )
                    }
                }
            }

            // 5. Attachments
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Attachments (LPO, Receipts, Photos)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                        Button(
                            onClick = { filePickerLauncher.launch("*/*") },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondaryContainer, contentColor = MaterialTheme.colorScheme.onSecondaryContainer)
                        ) {
                            Icon(Icons.Default.AttachFile, contentDescription = null)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Select Files to Attach", fontWeight = FontWeight.Bold)
                        }

                        if (selectedFiles.isNotEmpty()) {
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                selectedFiles.forEach { file ->
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("📎 ${file.name}", fontSize = 13.sp, maxLines = 1, modifier = Modifier.weight(1f))
                                        IconButton(onClick = { selectedFiles = selectedFiles - file }) {
                                            Icon(Icons.Default.Close, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(16.dp))
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 6. Submit Button
            item {
                val canPlaceOrder = if (useManualEntry) {
                    manualName.isNotBlank() && manualPhone.isNotBlank() && cart.isNotEmpty()
                } else {
                    selectedCustomer != null && cart.isNotEmpty()
                }

                Button(
                    onClick = {
                        if (useManualEntry) {
                            // Place order with manual customer details
                            viewModel.placeOrder(
                                customerId = null,
                                customerName = manualName,
                                customerPhone = manualPhone,
                                shippingAddress = shippingAddress.ifEmpty { manualAddress },
                                latitude = location.first,
                                longitude = location.second,
                                paidAmount = paidAmount.toDoubleOrNull() ?: 0.0,
                                paymentTerms = paymentTerms,
                                specialInstructions = specialInstructions,
                                files = selectedFiles
                            )
                        } else {
                            // Place order with selected customer
                            viewModel.placeOrder(
                                customerId = selectedCustomer?.id,
                                customerName = selectedCustomer?.name ?: "",
                                customerPhone = selectedCustomer?.phone ?: "",
                                shippingAddress = shippingAddress,
                                latitude = location.first,
                                longitude = location.second,
                                paidAmount = paidAmount.toDoubleOrNull() ?: 0.0,
                                paymentTerms = paymentTerms,
                                specialInstructions = specialInstructions,
                                files = selectedFiles
                            )
                        }
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(52.dp),
                    shape = RoundedCornerShape(12.dp),
                    enabled = canPlaceOrder && !isLoading
                ) {
                    if (isLoading) {
                        CircularProgressIndicator(modifier = Modifier.size(24.dp), color = MaterialTheme.colorScheme.onPrimary)
                    } else {
                        Icon(Icons.Default.Send, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Place and Sync Order", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    }
                }
            }
        }
    }

    // Dialog for creating a new customer (from search mode)
    if (showCreateCustomerDialog) {
        AlertDialog(
            onDismissRequest = { showCreateCustomerDialog = false },
            title = { Text("Create New Customer", fontWeight = FontWeight.Bold) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = newCustomerName,
                        onValueChange = { newCustomerName = it },
                        label = { Text("Customer Name") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    )
                    OutlinedTextField(
                        value = newCustomerPhone,
                        onValueChange = { newCustomerPhone = it },
                        label = { Text("Customer Phone") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    )
                    OutlinedTextField(
                        value = newCustomerAddress,
                        onValueChange = { newCustomerAddress = it },
                        label = { Text("Shipping Address") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        if (newCustomerName.isNotBlank() && newCustomerPhone.isNotBlank()) {
                            viewModel.createCustomer(newCustomerName, newCustomerPhone, newCustomerAddress)
                            // After creation, selectedCustomer will be set automatically in ViewModel
                            showCreateCustomerDialog = false
                            // Refresh search list
                            viewModel.searchCustomers(customerSearch)
                            newCustomerName = ""
                            newCustomerPhone = ""
                            newCustomerAddress = ""
                            Toast.makeText(context, "Customer created and selected!", Toast.LENGTH_SHORT).show()
                        }
                    },
                    enabled = newCustomerName.isNotBlank() && newCustomerPhone.isNotBlank()
                ) {
                    Text("Save")
                }
            },
            dismissButton = {
                TextButton(onClick = { showCreateCustomerDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }
}
