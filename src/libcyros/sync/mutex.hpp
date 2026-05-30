#pragma once

namespace cyros
{
   class Mutex
   {
   public:
      Mutex() = default;
      void Lock();
      void Unlock();
   };
}
