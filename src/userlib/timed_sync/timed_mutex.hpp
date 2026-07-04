#pragma once

#include <cyros/sync/mutex.hpp>
#include <cyros/time.hpp>

namespace cyros
{
   class TimedMutex : public Mutex
   {
   public:
      bool TryLockFor(TickDuration timeout);
   };
}
