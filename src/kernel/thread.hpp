#pragma once

#include <cortos/kernel.hpp>

namespace cortos
{
   class Thread
   {
   public:
      Thread() = default;
      void Start();
   };
}
