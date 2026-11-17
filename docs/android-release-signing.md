# Android release signing preparation

The debug APK is signed with a local debug key and is intended for testing. No release APK is distributed by this repository.

Before distribution, identify the owner of the existing release key and confirm the signing certificate fingerprint of any installed release. Verify package identity and upgrade compatibility on a test device. Decide whether a new key is appropriate for a new distribution or whether the existing key must be retained for updates.

Keep the release keystore, passwords and recovery copies in an access-controlled secret manager outside the checkout and build artifacts. Limit signing access, document key recovery and rotation, and use a protected release environment if automated signing is later approved. Verify the signed artifact and certificate with Android build tools and record checksums and provenance before publication. Never store signing material in Git, issue text, build logs or public CI artifacts.

Physical-device capture, location, ZIP export, separate file sharing, upgrade and signing tests are pending. The package identifier is currently `com.example.streetview`; changing it affects application identity and requires a separate migration decision.
