package com.example.data.remote

import com.example.data.local.GyroPulsePreferences
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

object RetrofitClient {
    private var currentBaseUrl: String? = null
    private var currentApi: GyroPulseApi? = null

    @Synchronized
    fun getApi(prefs: GyroPulsePreferences): GyroPulseApi {
        val baseUrl = prefs.getServerUrl()

        if (currentApi == null || currentBaseUrl != baseUrl) {
            currentBaseUrl = baseUrl
            val okHttpClient = OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .addInterceptor(object : Interceptor {
                    override fun intercept(chain: Interceptor.Chain): Response {
                        val originalRequest = chain.request()
                        val builder = originalRequest.newBuilder()
                        
                        val currentKey = prefs.getApiKey()
                        val userId = prefs.getUserId()
                        val originalUrl = originalRequest.url
                        val newUrlBuilder = originalUrl.newBuilder()
                        
                        // 🔥 Skip adding API key / user_id for login requests
                        if (!originalUrl.encodedPath.contains("/api/login")) {
                            if (!currentKey.isNullOrEmpty()) {
                                builder.addHeader("X-API-Key", currentKey)
                                builder.addHeader("X-Device-UUID", prefs.getDeviceId())
                            }
                            if (userId != null && userId != -1) {
                                newUrlBuilder.addQueryParameter("user_id", userId.toString())
                            }
                        }
                        builder.url(newUrlBuilder.build())
                        return chain.proceed(builder.build())
                    }
                })
                .addInterceptor(HttpLoggingInterceptor().apply {
                    level = HttpLoggingInterceptor.Level.NONE
                })
                .build()

            val retrofit = Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(okHttpClient)
                .build()

            currentApi = retrofit.create(GyroPulseApi::class.java)
        }
        return currentApi!!
    }

    @Synchronized
    fun reset() {
        currentApi = null
        currentBaseUrl = null
    }
}
