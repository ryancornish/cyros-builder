#pragma once

#include <cyros/kernel.hpp>

namespace cyros
{
   class Thread
   {
   public:
      Thread() = default;
      void Start();
   };
}
