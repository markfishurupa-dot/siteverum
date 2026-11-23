plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.example.streetview"
    compileSdk {
        version = release(36)
    }

    defaultConfig {
        applicationId = "com.example.streetview"
        minSdk = 26
        targetSdk = 36
        versionCode = 131
        versionName = "1.3.1"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    kotlinOptions {
        jvmTarget = "11"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    implementation("com.google.android.gms:play-services-location:21.3.0")
    val camerax_version = "1.4.0" // or 1.3.x;

    implementation("androidx.camera:camera-core:$camerax_version")
    implementation("androidx.camera:camera-camera2:$camerax_version")
    implementation("androidx.camera:camera-lifecycle:$camerax_version")
    implementation("androidx.camera:camera-video:$camerax_version")

    // If you later want PreviewView UI preview:
    implementation("androidx.camera:camera-view:$camerax_version")

    // LifecycleService already in androidx.lifecycle:lifecycle-service (usually pulled in)
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    // CameraX
    implementation("androidx.camera:camera-core:1.4.0")
    implementation("androidx.camera:camera-camera2:1.4.0")
    implementation("androidx.camera:camera-lifecycle:1.4.0")
    implementation("androidx.camera:camera-video:1.4.0")
    implementation("androidx.camera:camera-view:1.4.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")

    // Location (you already have this)
    implementation("com.google.android.gms:play-services-location:21.3.0")

    // Background archiving (ZIP) without freezing UI
    implementation("androidx.work:work-runtime-ktx:2.9.0")

    // Material icons (⋮ menu)
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.fragment:fragment-ktx:1.6.2")
}