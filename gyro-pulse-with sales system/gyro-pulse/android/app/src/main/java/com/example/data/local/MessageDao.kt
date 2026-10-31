package com.example.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface MessageDao {
    @Query("SELECT * FROM messages ORDER BY createdAt DESC")
    fun getAllMessagesFlow(): Flow<List<Message>>

    @Query("SELECT * FROM messages WHERE synced = 0 AND isReply = 0")
    suspend fun getPendingMessages(): List<Message>

    // NEW: Get all messages (for full upload)
    @Query("SELECT * FROM messages ORDER BY createdAt ASC")
    suspend fun getAllMessages(): List<Message>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(message: Message): Long

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(messages: List<Message>)

    @Query("UPDATE messages SET synced = :synced, serverId = :serverId WHERE id = :id")
    suspend fun updateSyncStatus(id: Long, synced: Boolean, serverId: Int?)

    // NEW: Update only serverId
    @Query("UPDATE messages SET serverId = :serverId WHERE id = :id")
    suspend fun updateServerId(id: Long, serverId: Int)

    @Query("DELETE FROM messages WHERE id = :id")
    suspend fun deleteById(id: Long)

    @Query("SELECT * FROM messages WHERE serverId = :serverId LIMIT 1")
    suspend fun getMessageByServerId(serverId: Int): Message?

    // NEW: Get all existing server IDs to avoid duplicates
    @Query("SELECT serverId FROM messages WHERE serverId IS NOT NULL")
    suspend fun getAllServerIds(): List<Int>

    @Query("DELETE FROM messages")
    suspend fun clearAll()
}