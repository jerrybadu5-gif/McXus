plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Push notifications need your Firebase project's google-services.json in this folder (docs/FIREBASE-PUSH.md).
// Without it the app builds and works the same, just without pushes.
if (file("google-services.json").exists()) apply(plugin = "com.google.gms.google-services")

android {
    namespace = "pg.mcxus.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "pg.mcxus.app"
        minSdk = 26 // Android 8.0
        targetSdk = 35
        versionCode = 7
        versionName = "0.6.0-m5"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk {
            // Native encryption library (OpenMLS) is built for these phone CPU types.
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    signingConfigs {
        // Shared DEBUG key (in the repo on purpose) so every test build installs over the previous one.
        // Never used for Play Store releases; a release key is created separately and kept secret.
        getByName("debug") {
            storeFile = rootProject.file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        buildConfig = true
        compose = true
    }
    lint {
        abortOnError = true
        warningsAsErrors = false
        disable += "GradleDependency" // versions are pinned on purpose; Dependabot proposes upgrades
    }
    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            // Crypto tests load the laptop build of the encryption library (cargo build in ../crypto); they are
            // skipped when it has not been built.
            it.systemProperty("jna.library.path", rootProject.file("../crypto/target/debug").absolutePath)
            // Server and screenshot tests download Robolectric's Android image (~350 MB): only with -Pe2e.
            if (!project.hasProperty("e2e")) it.exclude("**/ChatEngineServerTest*", "**/ScreenshotTour*")
            listOf("MCXUS_E2E_SERVER", "MCXUS_SCREENSHOTS", "MCXUS_ADMIN_TOKEN").forEach { name ->
                System.getenv(name)?.let { v -> it.environment(name, v) }
            }
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("com.google.zxing:core:3.5.3") // QR code for the handover PIN
    implementation("net.java.dev.jna:jna:5.15.0@aar") // used by the generated OpenMLS bindings
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging") // content-free "new message" pushes
    implementation("org.osmdroid:osmdroid-android:6.1.20") // OpenStreetMap map to set a meet-up / delivery point (Apache-2.0)
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303") // real org.json for JVM unit tests
    testImplementation("net.java.dev.jna:jna:5.15.0") // JVM build of JNA for crypto tests on the laptop
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    testImplementation("org.robolectric:robolectric:4.14.1") // Android APIs (SQLite, Base64) on the laptop's JVM
    testImplementation("androidx.test:core:1.6.1")
    testImplementation(composeBom)
    testImplementation("androidx.compose.ui:ui-test-junit4") // screenshots of the screens on the laptop

    androidTestImplementation(composeBom)
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}
