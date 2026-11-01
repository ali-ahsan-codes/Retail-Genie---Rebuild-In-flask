plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "com.example"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.retailgenie.hybrid.pilot"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1-pilot"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    // No legacy room/preferences, GPC, embedded secrets, APIs, viewmodels or sync workers.
    sourceSets {
        getByName("main").java.setSrcDirs(listOf("src/main/java/com/example/hybrid"))
        getByName("test").java.setSrcDirs(listOf("src/hybridTest/java"))
        getByName("androidTest").java.setSrcDirs(listOf("src/androidTest/java/com/example/hybrid"))
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildTypes {
        debug { applicationIdSuffix = ".debug" }
        release { isMinifyEnabled = false } // unsigned: production signing is a separate gate
    }
}
kotlin {
    jvmToolchain(17)
    sourceSets.getByName("main").kotlin.setSrcDirs(listOf("src/main/java/com/example/hybrid"))
    sourceSets.getByName("test").kotlin.setSrcDirs(listOf("src/hybridTest/java"))
    sourceSets.getByName("androidTest").kotlin.setSrcDirs(listOf("src/androidTest/java/com/example/hybrid"))
}
dependencies {
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("junit:junit:4.13.2")
}
