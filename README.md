# cyros-builder
Standalone Python-based build system custom tailored to build Cyros

## Dependencies
_Combined dependency list for both this project, and Cyros. For now I am attaching ubuntu hints for installation here
purely for my convenience and bookkeeping_
### cyros-builder
- `pipx`: `sudo apt install pipx`
### cyros
#### Libraries
- `boost.context`: `sudo apt install libboost-context-dev`
- `googletest`: `sudo apt install libgtest-dev`
#### Toolchains
`sudo add-apt-repository ppa:ubuntu-toolchain-r/test; sudo apt update`
- `gcc-15`: `sudo apt install gcc-15`
- `g++-15`: `sudo apt install g++-15`
#### Other
- `clangd`: `sudo apt install clangd`


## Install
```bash
pipx install -e cyros-builder
```
