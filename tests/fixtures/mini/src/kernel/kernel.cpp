#include "mini/kernel.hpp"
#include "kernel_detail.hpp"
namespace mini { int kernel_entry() { return detail::seed(); } }
