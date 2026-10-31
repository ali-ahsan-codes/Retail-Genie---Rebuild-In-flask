package com.example.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "messages")
data class Message(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val type: String,                 // "text","voice","image","video","barcode"
    val content: String?,             // text or barcode data
    val mediaUri: String?,            // local file path or URI (stored in filesDir)
    val latitude: Double?,
    val longitude: Double?,
    val createdAt: Long,              // timestamp in milliseconds
    val synced: Boolean = false,      // true if uploaded to server
    val serverId: Int? = null,        // server-assigned ID
    val isReply: Boolean = false,     // true if this is an admin reply
    val replyMessage: String? = null  // content of the reply
)
