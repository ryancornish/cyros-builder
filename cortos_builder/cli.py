#!/usr/bin/env python3

import argparse




def main() -> int:
   parser = argparse.ArgumentParser(description="TODO")
   subparser = parser.add_subparsers(required=True, dest="command")
   build_parser = subparser.add_parser("build")
   build_parser.add_argument("-p", "--profile", required=True)

   #parser.add_argument("", required=True, help="")
   #parser.add_argument("", action="store_true", default=False, help="")
   #parser.add_argument("", nargs="*", help="", default=["", "", "", ""])

   args = parser.parse_args()


   print("Hello from cortos-builder")
   return 0


if __name__ == "__main__":
   raise SystemExit(main())