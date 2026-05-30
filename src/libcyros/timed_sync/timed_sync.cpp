#include <cyros/timed_sync/timed_mutex.hpp>

namespace cyros
{
   bool TimedMutex::TryLockFor(TickDuration timeout)
   {
      (void)timeout;
      return true;
   }
}
