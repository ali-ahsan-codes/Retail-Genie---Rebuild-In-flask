package com.example.data.remote

import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.http.*

interface GyroPulseApi {
    // -------- AUTH --------
    @POST("api/login")
    suspend fun login(@Body request: RequestBody): ResponseBody

    // -------- LEGACY (messaging) --------
    @GET("api/ping")
    suspend fun ping(@Query("user_id") userId: Int?): ResponseBody

    @Multipart
    @POST("api/message")
    suspend fun sendMessage(
        @Part("type") type: RequestBody,
        @Part("content") content: RequestBody?,
        @Part("latitude") latitude: RequestBody?,
        @Part("longitude") longitude: RequestBody?,
        @Part("device_id") deviceId: RequestBody?,
        @Part("user_id") userId: RequestBody?,
        @Part file: MultipartBody.Part?
    ): ResponseBody

    @POST("api/sync")
    suspend fun syncMessages(@Body messages: RequestBody): ResponseBody

    @GET("api/responses")
    suspend fun getResponses(@Query("limit") limit: Int = 20): ResponseBody

    @GET("api/messages/inbox")
    suspend fun getInbox(
        @Query("user_id") userId: Int,
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
        @Query("unread_only") unreadOnly: Boolean = false
    ): ResponseBody

    @POST("api/messages/read/{id}")
    suspend fun markMessageRead(@Path("id") id: Int): ResponseBody

    @GET("api/messages/poll")
    suspend fun pollMessages(
        @Query("user_id") userId: Int,
        @Query("since") since: String?
    ): ResponseBody

    @GET("api/sync/status")
    suspend fun getSyncStatus(@Query("user_id") userId: Int): ResponseBody

    @POST("api/sync/upload_all")
    suspend fun uploadAllMessages(@Body request: RequestBody): ResponseBody

    @GET("api/user/messages/export")
    suspend fun exportUserMessages(
        @Query("user_id") userId: Int,
        @Query("from") from: String?,
        @Query("to") to: String?,
        @Query("type") type: String?,
        @Query("limit") limit: Int = 1000,
        @Query("offset") offset: Int = 0
    ): ResponseBody

    // -------- NEW SALES --------
    @GET("api/products/sync")
    suspend fun syncProducts(
        @Query("user_id") userId: Int,
        @Query("since") since: String?,
        @Query("city_id") cityId: Int?
    ): ResponseBody

    @GET("api/products/search")
    suspend fun searchProducts(
        @Query("user_id") userId: Int,
        @Query("q") query: String?,
        @Query("barcode") barcode: String?
    ): ResponseBody

    @GET("api/customers/search")
    suspend fun searchCustomers(
        @Query("user_id") userId: Int,
        @Query("q") query: String?
    ): ResponseBody

    @POST("api/customers")
    suspend fun createCustomer(
        @Body request: RequestBody
    ): ResponseBody

    @POST("api/orders/place")
    suspend fun placeOrder(
        @Body request: RequestBody
    ): ResponseBody

    @GET("api/settings")
    suspend fun getSettings(): ResponseBody

    // -------- OFFLINE-FIRST GPC & MOBILE SYNC --------
    @GET("health")
    suspend fun health(): ResponseBody

    @GET("api/mobile/sync")
    suspend fun mobileSync(): ResponseBody

    @POST("api/device/commands/acknowledge")
    suspend fun acknowledgeCommands(@Body request: RequestBody): ResponseBody
}
