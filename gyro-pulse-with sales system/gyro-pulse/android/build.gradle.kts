// Isolated connected-mode build. Upstream standalone sources remain on disk, not in this APK.
plugins {
    id("com.android.application") version "8.9.2" apply false
    id("org.jetbrains.kotlin.android") version "2.1.20" apply false
}
