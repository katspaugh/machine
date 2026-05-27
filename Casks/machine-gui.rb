# This cask lives in the main repo as a reference. The published tap is
# katspaugh/homebrew-machine — copy this file into its Casks/ dir and bump
# version/sha256 on each release. See docs/TAP.md.
cask "machine-gui" do
  version "0.1.2"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://github.com/katspaugh/machine/releases/download/v#{version}/machine_#{version}_universal.dmg"
  name "machine"
  desc "Desktop GUI for machine — manage per-project Lima VMs"
  homepage "https://runmachine.dev"

  # The GUI shells out to the `machine` CLI for every action.
  depends_on formula: "katspaugh/machine/machine"
  depends_on macos: ">= :monterey"

  app "machine.app"

  zap trash: [
    "~/Library/Application Support/dev.runmachine.gui",
    "~/Library/Caches/dev.runmachine.gui",
    "~/Library/Preferences/dev.runmachine.gui.plist",
    "~/Library/Saved Application State/dev.runmachine.gui.savedState",
  ]
end
