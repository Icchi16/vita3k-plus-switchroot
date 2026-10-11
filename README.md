# Vita3K Plus for Switchroot Noble

Builds a Linux ARM64 Release tar archive on GitHub Actions using ubuntu-24.04-arm.
No local Linux environment or build space on the Switch is required.

Source is pinned to nckstwrt/Vita3K-Plus commit e2331f809a50f093ca1e2920e47e7dba67d08f3d
(all-enhancements). Qt 6.11 ARM64 is downloaded from the official Qt repository.
Build support supplies the fork's missing metadata header and bounded LibAtrac9 API,
and guards the empty filesystem path on early CLI exits. These patches are included
under patches/. The existing local RecoLove graphics patch is not applied.

The workflow runs when its workflow/scripts are pushed, or from Actions > Run workflow.
Successful output contains Vita3K-Plus-Noble-ARM64.tar.gz and its SHA256 checksum.
Compiled inputs are retained for 14 days. To retry packaging without compiling,
use Run workflow and enter the earlier run ID in package_from_run. Source,
Qt version and build recipe must match the retained inputs.
An artifact is uploaded only after ELF architecture, dependency and relocated CLI checks pass.

Extract the tar on Switchroot Noble and run ./launch.sh in a desktop session.
Qt and required non-driver libraries are included. Host glibc and GPU drivers are used.
Rendering and gameplay on Tegra are not verified by the cloud build.

Configuration and compilation failures stop the workflow. Diagnostic logs are uploaded on failure.
This repository contains build automation; games, firmware and user data are not included.
