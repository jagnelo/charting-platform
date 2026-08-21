# fix/arm64-ci-emulation

This branch repairs the independent GitHub platform gate. The exact master
replay at `5124146980b37f6d6b5080d737f801933700b0c5` passed backend, frontend,
and Playwright validation but failed at the final ARM64 image stage with
`exec format error`: GitHub's amd64 runner had no binfmt/QEMU registration for
executing `linux/arm64` Dockerfile `RUN` instructions.

The workflow change registers Docker's QEMU action immediately before the
authoritative gate. This is CI-only infrastructure; native ARM64 Mac builds
and RPi deployment tooling are not changed.
