#!/usr/bin/env bash

echo "Configuring repo. I hope you use Ubuntu..."

set -x
set -e

#####
# corpus/

echo "Configuring corpus creation tools"
pushd corpus/corpus-creation/
  echo "  Tools for extraction via static analysis"
  pushd static-analysis/
    pushd java/regex-extractor
    ./build.pl
    popd

    pushd js
    ./build.pl
    popd

    pushd ts
    ./build.pl
    popd

    pushd python
    ./build.pl
    popd
	popd

  echo "  Tools for extraction via program instrumentation"
  pushd program-instrumentation
		pushd run/
		./build.pl
		popd
	popd

#####
# measurement-instruments/

echo "Configuring regex measurement tools"

echo "Installing nvm (for vuln-regex-detector)"
installNVM()

echo "Installing wine (so we can run AutomataCLI.exe)"
installWine()

pushd measurement-instruments/
./build.pl

  echo "  Configuring worst-case performance detection"
  pushd worst-case-performance/
  ./build.pl
  popd
popd

echo "Configuration complete. I hope everything works!"

############
# Functions
############

installWine() {
  if command_exists wine ; then
    echo "wine already installed"
    return
  fi
  echo "Installing wine -- sudo required"
  sudo dpkg --add-architecture i386
  wget -qO - https://dl.winehq.org/wine-builds/winehq.key | sudo apt-key add -
  sudo apt-add-repository 'deb https://dl.winehq.org/wine-builds/ubuntu/ xenial main'
  sudo apt-get update
  sudo apt-get install --install-recommends winehq-stable

  if command_exists wine ; then
    echo "wine successfully installed"
    return
  fi
  echo "Could not install wine"
  exit 1
}

installNVM() {
  if command_exists nvm ; then
    echo "nvm already installed"
    return
  fi
  echo "Installing nvm"

  # TODO My notes say we need this for the vuln-regex-detector installation. Do we?
  echo "Installing nvm"
  curl -o- https://raw.githubusercontent.com/creationix/nvm/v0.33.8/install.sh | bash
  # Source so nvm is in path now
  touch ~/.bashrc && . ~/.bashrc
}

command_exists () {
    type "$1" &> /dev/null ;
}