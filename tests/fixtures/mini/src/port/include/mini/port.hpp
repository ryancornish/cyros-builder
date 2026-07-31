#pragma once
// Deliberately NOT marked MINI_PUBLIC: this is the internal symbol the lto tests
// assert becomes local after --localize-hidden.
namespace mini { void port_init(); }
