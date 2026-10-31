package com.example.data.local

import android.content.Context
import org.json.JSONObject

/** Persist before network I/O; user-scoped identity survives timeouts and process restarts. */
class OrderOutbox(context: Context) {
    private val storage = context.getSharedPreferences("order_outbox", Context.MODE_PRIVATE)
    fun save(userId: Int, payload: JSONObject) = synchronized(lock) {
        check(storage.edit().putString("$userId:${payload.getString("client_order_id")}", payload.toString()).commit()) {
            "Could not persist offline order"
        }
    }
    fun remove(userId: Int, clientId: String) = synchronized(lock) {
        check(storage.edit().remove("$userId:$clientId").commit())
    }
    fun pending(userId: Int): List<JSONObject> = synchronized(lock) {
        storage.all.filterKeys { it.startsWith("$userId:") }.values.map { JSONObject(it as String) }
    }
    companion object { private val lock = Any() }
}
