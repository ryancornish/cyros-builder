#include <cortos/timed_sync/timed_mutex.hpp>

namespace cortos
{
   bool TimedMutex::TryLockFor(TickDuration timeout)
   {
      (void)timeout;
      return true;
   }
}
