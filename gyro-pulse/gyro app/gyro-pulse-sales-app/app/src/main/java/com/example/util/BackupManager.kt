package com.example.util

import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import android.util.Log
import androidx.core.content.FileProvider
import com.example.data.local.AppDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.*
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

object BackupManager {
    private const val TAG = "BackupManager"
    private const val BACKUP_METADATA = "metadata.json"
    private const val FILES_DIR = "files"
    private const val DB_DIR = "db"

    /**
     * Export backup to a ZIP file in the app's cache, then share/return it.
     */
    suspend fun exportBackup(context: Context, prefs: SharedPreferences): Uri = withContext(Dispatchers.IO) {
        val cacheDir = File(context.cacheDir, "backup_temp")
        cacheDir.mkdirs()
        cacheDir.deleteRecursively() // clean slate
        cacheDir.mkdirs()

        // 1. Close database to flush WAL to the main db file
        try {
            AppDatabase.getDatabase(context).close()
            // Wait brief moment for SQLite to release locks
            Thread.sleep(150)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to close DB cleanly before export", e)
        }

        // 2. Gather database files
        val dbFile = context.getDatabasePath("gyropulse_database")
        val dbFiles = dbFile.parentFile?.listFiles { _, name ->
            name.startsWith(dbFile.name)
        } ?: emptyArray()

        // 3. Write metadata.json
        val appVersionName = try {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName
        } catch (e: Exception) {
            "1.0.0"
        }

        val meta = JSONObject().apply {
            put("app_version", appVersionName)
            put("timestamp", System.currentTimeMillis())
            put("user_id", prefs.getInt("user_id", -1))
            put("device_name", prefs.getString("device_name", ""))
            put("server_url", prefs.getString("server_url", ""))
            put("api_key", prefs.getString("api_key", ""))
            put("device_id", prefs.getString("device_id", ""))
        }
        val metaFile = File(cacheDir, BACKUP_METADATA)
        metaFile.writeText(meta.toString())

        // 4. Create ZIP file in cache
        val zipFile = File(context.cacheDir, "gyropulse_backup_${System.currentTimeMillis()}.zip")
        ZipOutputStream(BufferedOutputStream(FileOutputStream(zipFile))).use { zos ->
            // Add metadata
            addToZip(zos, metaFile, BACKUP_METADATA)

            // Add database files
            dbFiles.forEach { f ->
                if (f.isFile) {
                    addToZip(zos, f, "$DB_DIR/${f.name}")
                }
            }

            // Add all files from filesDir
            val filesDir = context.filesDir
            filesDir.listFiles()?.forEach { f ->
                if (f.isFile) {
                    addToZip(zos, f, "$FILES_DIR/${f.name}")
                }
            }
        }

        // Clean up temp folder
        cacheDir.deleteRecursively()

        // Return the ZIP URI using FileProvider
        FileProvider.getUriForFile(context, "com.example.fileprovider", zipFile)
    }

    private fun addToZip(zos: ZipOutputStream, file: File, entryName: String) {
        if (!file.exists()) return
        val buffer = ByteArray(8192)
        zos.putNextEntry(ZipEntry(entryName))
        BufferedInputStream(FileInputStream(file)).use { bis ->
            var bytesRead: Int
            while (bis.read(buffer).also { bytesRead = it } != -1) {
                zos.write(buffer, 0, bytesRead)
            }
        }
        zos.closeEntry()
    }

    /**
     * Import backup from a ZIP file Uri.
     */
    suspend fun importBackup(context: Context, zipUri: Uri): Boolean = withContext(Dispatchers.IO) {
        try {
            val restoreTempDir = File(context.cacheDir, "restore_temp")
            restoreTempDir.mkdirs()
            restoreTempDir.deleteRecursively() // clean slate
            restoreTempDir.mkdirs()

            // 1. Extract ZIP to temp folder
            val inputStream = context.contentResolver.openInputStream(zipUri) ?: return@withContext false
            ZipInputStream(BufferedInputStream(inputStream)).use { zis ->
                var entry = zis.nextEntry
                while (entry != null) {
                    val fileName = entry.name
                    val targetFile = File(restoreTempDir, fileName)
                    if (entry.isDirectory) {
                        targetFile.mkdirs()
                    } else {
                        targetFile.parentFile?.mkdirs()
                        BufferedOutputStream(FileOutputStream(targetFile)).use { fos ->
                            val buffer = ByteArray(8192)
                            var len: Int
                            while (zis.read(buffer).also { len = it } != -1) {
                                fos.write(buffer, 0, len)
                            }
                        }
                    }
                    zis.closeEntry()
                    entry = zis.nextEntry
                }
            }

            // 2. Close active DB connection
            try {
                AppDatabase.getDatabase(context).close()
                Thread.sleep(250) // wait for DB release
            } catch (e: Exception) {
                Log.e(TAG, "Error closing DB before import replacement", e)
            }

            // 3. Replace Database files
            val dbFile = context.getDatabasePath("gyropulse_database")
            val dbFolder = dbFile.parentFile
            if (dbFolder != null) {
                // Delete current database files
                val currentDbFiles = dbFolder.listFiles { _, name ->
                    name.startsWith(dbFile.name)
                } ?: emptyArray()
                currentDbFiles.forEach { it.delete() }

                // Copy restored database files
                val tempDbFolder = File(restoreTempDir, DB_DIR)
                if (tempDbFolder.exists()) {
                    tempDbFolder.listFiles()?.forEach { file ->
                        val targetName = file.name.replace("tooliport_database", "gyropulse_database")
                        val destFile = File(dbFolder, targetName)
                        file.copyTo(destFile, overwrite = true)
                    }
                }
            }

            // 4. Replace filesDir files
            val tempFilesDir = File(restoreTempDir, FILES_DIR)
            if (tempFilesDir.exists()) {
                val filesDir = context.filesDir
                filesDir.listFiles()?.forEach { if (it.isFile) it.delete() }
                tempFilesDir.listFiles()?.forEach { file ->
                    if (file.isFile) {
                        file.copyTo(File(filesDir, file.name), overwrite = true)
                    }
                }
            }

            // 5. Restore metadata to SharedPreferences
            val metaFile = File(restoreTempDir, BACKUP_METADATA)
            if (metaFile.exists()) {
                try {
                    val json = JSONObject(metaFile.readText())
                    val prefs = context.getSharedPreferences("gyropulse_prefs", Context.MODE_PRIVATE)
                    prefs.edit().apply {
                        val userId = json.optInt("user_id", -1)
                        if (userId != -1) {
                            putInt("user_id", userId)
                        } else {
                            remove("user_id")
                        }
                        putString("device_name", json.optString("device_name", "Warehouse-Scanner"))
                        putString("server_url", json.optString("server_url", "https://app2.tooliport.com/"))
                        putString("api_key", json.optString("api_key", ""))
                        putString("device_id", json.optString("device_id", ""))
                        apply()
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error restoring SharedPreferences from backup", e)
                }
            }

            // Clean up temp
            restoreTempDir.deleteRecursively()
            true
        } catch (e: Exception) {
            Log.e(TAG, "Import backup failed", e)
            false
        }
    }
}
