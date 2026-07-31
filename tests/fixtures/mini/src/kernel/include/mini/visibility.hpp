#pragma once

// Mark a declaration as part of the public ABI. Everything else is hidden by
// -fvisibility=hidden in the lto toolchain and localized in the merged archive.
#if defined(__GNUC__) || defined(__clang__)
#  define MINI_PUBLIC __attribute__((visibility("default")))
#else
#  define MINI_PUBLIC
#endif
