package com.example.sync

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.example.data.repository.GyroPulseRepository
import com.example.data.local.AppDatabase
import com.example.data.local.GyroPulsePreferences

class SyncWorker(
    context: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(context, workerParams) {

    override suspend fun doWork(): Result {
        Log.d("SyncWorker", "Starting periodic background sync")
        val database = AppDatabase.getDatabase(applicationContext)
        val messageDao = database.messageDao()
        val inboxMessageDao = database.inboxMessageDao()
        val preferencesManager = GyroPulsePreferences(applicationContext)
        val repository = GyroPulseRepository(applicationContext, messageDao, inboxMessageDao, preferencesManager)

        if (preferencesManager.getApiKey().isNullOrEmpty()) {
            Log.d("SyncWorker", "No API Key saved, skipping sync")
            return Result.success()
        }

        val userId = preferencesManager.getUserId()
        if (userId == null || userId == -1) {
            Log.d("SyncWorker", "No valid user ID, skipping sync")
            return Result.success()
        }

        return try {
            if (!repository.flushOrderOutbox()) return Result.retry()

            // 1. Check sync status
            val status = repository.checkSyncStatus(userId)
            if (status != null && status.uploadRequired) {
                Log.d("SyncWorker", "Upload required, uploading all messages")
                val uploadResult = repository.uploadAllMessages(userId)
                if (uploadResult == null || !uploadResult.success) {
                    Log.w("SyncWorker", "Upload all failed")
                    return Result.retry()
                }
            }

            // 2. Poll new messages
            val since = preferencesManager.getLastPollTimestamp()
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
                        preferencesManager.setLastPollTimestamp(iso)
                    }
                }
            }

            // 3. Perform normal batch sync (pending messages)
            repository.performBatchSync()
            repository.fetchAdminReplies()
            repository.fetchInbox(userId)

            Log.d("SyncWorker", "Background sync completed successfully")
            Result.success()
        } catch (e: Exception) {
            Log.e("SyncWorker", "Background sync failed", e)
            Result.retry()
        }
    }
}
