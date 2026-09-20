#include "mini/port.hpp"
#include "mini/port_internal.hpp"   // internal tree: compiles only if it is on the path
namespace mini { void port_init() { (void)port_internal_value; } }
