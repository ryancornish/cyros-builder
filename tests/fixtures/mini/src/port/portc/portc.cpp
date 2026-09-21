/* Includes a base-layer header, which only resolves because `extends` brought
 * the base's private_includes along. */
#include "corelayer.hpp"

int mini_port_mcu_marker()
{
   return MINI_CORE_MARKER + 1;
}
