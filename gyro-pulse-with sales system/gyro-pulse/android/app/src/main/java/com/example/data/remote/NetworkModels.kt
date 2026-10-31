package com.example.data.remote

// Login
data class LoginResponse(
    val user_id: Int,
    val api_key: String,
    val username: String,
    val role: String,
    val city_id: Int?
)

// Products
data class ProductResponse(
    val id: Int,
    val name: String,
    val sku: String?,
    val barcode: String?,
    val unit_price: Double,
    val tax_rate: Double,
    val current_warehouse_qty: Int,
    val description: String?,
    val image_url: String?,
    val is_active: Boolean = true
)

// Customers
data class CustomerResponse(
    val id: Int,
    val name: String,
    val phone: String,
    val email: String?,
    val billing_address: String?,
    val shipping_address: String?,
    val outstanding_balance: Double
)

// Order
data class OrderItemRequest(
    val product_id: Int,
    val qty: Int,
    val unit_price: Double,
    val note: String? = null
)

data class OrderPlaceResponse(
    val status: String,
    val order_id: Int,
    val message: String
)

// Legacy models
data class RegisterRequest(
    val deviceName: String
)

data class RegisterResponse(
    val apiKey: String,
    val userId: Int
)

data class PingResponse(
    val status: String,
    val userId: Int?
)

data class MessageResponse(
    val status: String,
    val messageId: Int?
)

data class SyncMessage(
    val type: String,
    val content: String?,
    val latitude: Double?,
    val longitude: Double?,
    val deviceId: String?,
    val createdAt: Long? = null
)

data class SyncResponse(
    val accepted: List<Int>,
    val failed: List<Int>
)

data class AdminReplyItem(
    val id: Int,
    val message: String,
    val mediaUrl: String?,
    val createdAt: String,
    val read: Boolean
)

data class ResponsesResponse(
    val data: List<AdminReplyItem>,
    val total: Int
)

data class InboxMessage(
    val id: Int,
    val sender_id: Int,
    val sender_username: String,
    val content: String?,
    val media_url: String?,
    val created_at: String,
    val read: Boolean
)

data class InboxResponse(
    val messages: List<InboxMessage>,
    val total: Int
)

data class SettingsResponse(
    val currency: String,
    val tax_rate: Double,
    val tax_label: String
)

