#pragma once

#include <cortos/sync/mutex.hpp>
#include <cortos/time.hpp>

namespace cortos
{
   class TimedMutex : public Mutex
   {
   public:
      bool TryLockFor(TickDuration timeout);
   };
}
