package com.example.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "inbox_messages")
data class InboxMessageEntity(
    @PrimaryKey val id: Int,
    val senderId: Int,
    val senderUsername: String,
    val content: String?,
    val mediaUrl: String?,
    val createdAt: String,
    val read: Boolean
)
