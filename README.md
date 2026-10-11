# Vita3K Plus for Switchroot Noble

Builds a Linux ARM64 Release tar archive on GitHub Actions using ubuntu-24.04-arm.
No local Linux environment or build space on the Switch is required.

Source is pinned to nckstwrt/Vita3K-Plus commit e2331f809a50f093ca1e2920e47e7dba67d08f3d
(all-enhancements). Qt 6.11 ARM64 is downloaded from the official Qt repository.
The emulator source is unmodified; the existing local RecoLove patch is not applied.

The workflow runs when its workflow/scripts are pushed, or from Actions > Run workflow.
Successful output contains Vita3K-Plus-Noble-ARM64.tar.gz and its SHA256 checksum.
An artifact is uploaded only after ELF architecture, dependency and relocated CLI checks pass.

Extract the tar on Switchroot Noble and run ./launch.sh in a desktop session.
Qt and required non-driver libraries are included. Host glibc and GPU drivers are used.
Rendering and gameplay on Tegra are not verified by the cloud build.

Configuration and compilation failures stop the workflow. Diagnostic logs are uploaded on failure.
This repository contains build automation; games, firmware and user data are not included.
