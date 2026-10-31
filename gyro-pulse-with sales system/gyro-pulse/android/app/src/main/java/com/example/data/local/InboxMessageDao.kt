package com.example.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface InboxMessageDao {
    @Query("SELECT * FROM inbox_messages ORDER BY id DESC")
    fun getAllInboxMessagesFlow(): Flow<List<InboxMessageEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(messages: List<InboxMessageEntity>)

    @Query("UPDATE inbox_messages SET read = 1 WHERE id = :id")
    suspend fun markAsRead(id: Int)

    @Query("DELETE FROM inbox_messages")
    suspend fun clearAll()
}
