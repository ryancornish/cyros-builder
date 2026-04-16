export module cortos.sync;

export namespace cortos
{
   class Mutex
   {
   public:
      Mutex() = default;
      void Lock();
      void Unlock();
   };
}