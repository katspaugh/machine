# typed: false
# frozen_string_literal: true

# This formula lives in the main repo as a reference. The published tap is
# katspaugh/homebrew-machine — copy this file there and bump url/sha256/version
# on each release. See docs/TAP.md.
class Machine < Formula
  desc     "One isolated Lima VM per project — Docker, Node, agent CLIs, signed git"
  homepage "https://runmachine.dev"
  url      "https://github.com/katspaugh/machine/archive/refs/tags/v0.2.4.tar.gz"
  sha256   "5adc71b19207b5a2c97b273d1ab5c6d3a1eb8c267a9399a7bbf217507e5a6609"
  license  "MIT"
  head     "https://github.com/katspaugh/machine.git", branch: "main"

  depends_on "lima"
  depends_on "python@3.12"

  def install
    libexec.install Dir["*"]
    (bin/"machine").write <<~SH
      #!/bin/sh
      exec "#{Formula["python@3.12"].opt_bin}/python3.12" "#{libexec}/bin/machine" "$@"
    SH
    chmod 0555, bin/"machine"

    bash_completion.install libexec/"completions/machine.bash" => "machine"
    zsh_completion.install  libexec/"completions/_machine"
    fish_completion.install libexec/"completions/machine.fish"
  end

  def caveats
    <<~EOS
      Requires Lima >= 2.0 (template composition).

      Bootstrap your projects file:

        machine init
        $EDITOR ~/.config/machine/projects.toml

      Then check prerequisites and bring a project up:

        machine doctor
        machine up <project>

      Config:  ~/.config/machine/projects.toml
      State:   ~/.local/state/machine/
      Cache:   ~/.cache/machine/
    EOS
  end

  test do
    assert_match "machine", shell_output("#{bin}/machine --help")
    assert_match "init",    shell_output("#{bin}/machine --help")
  end
end
