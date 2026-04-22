#pragma once

namespace cortos
{
   class Mutex
   {
   public:
      Mutex() = default;
      void Lock();
      void Unlock();
   };
}
