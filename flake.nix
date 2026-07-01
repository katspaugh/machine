{
  description = "machine — one isolated Lima VM per project";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      version = "0.2.4";
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      lib = nixpkgs.lib;
      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        machine =
          # machine needs Lima >= 2.0 (template composition, `mode: data`
          # provisioning). Fail the build loudly if nixpkgs ever regresses.
          assert lib.assertMsg (lib.versionAtLeast pkgs.lima.version "2.0")
            "machine requires Lima >= 2.0, but nixpkgs has ${pkgs.lima.version}";
          pkgs.stdenv.mkDerivation {
            pname = "machine";
            inherit version;

            # Build from the flake's own source tree. `.git` is excluded from
            # flake sources, so the CLI's checkout detection stays false and
            # it uses XDG config/state dirs, same as under Homebrew.
            src = self;

            nativeBuildInputs = [
              pkgs.makeWrapper
              pkgs.installShellFiles
            ];

            dontBuild = true;
            doInstallCheck = true;

            installPhase = ''
              runHook preInstall

              mkdir -p $out/libexec/machine
              cp -R . $out/libexec/machine

              # Same shim as the Homebrew formula: pinned interpreter, Lima
              # on PATH. The script resolves templates/provision/files
              # relative to its own location under libexec.
              makeWrapper ${pkgs.python3}/bin/python3 $out/bin/machine \
                --add-flags "$out/libexec/machine/bin/machine" \
                --prefix PATH : ${pkgs.lima}/bin

              installShellCompletion --cmd machine \
                --bash completions/machine.bash \
                --zsh completions/_machine \
                --fish completions/machine.fish

              runHook postInstall
            '';

            # Mirrors the formula's `test do` block.
            installCheckPhase = ''
              runHook preInstallCheck
              $out/bin/machine --help | grep -q machine
              $out/bin/machine --help | grep -q init
              runHook postInstallCheck
            '';

            meta = {
              description = "One isolated Lima VM per project — Docker, Node, agent CLIs, signed git";
              homepage = "https://runmachine.dev";
              license = lib.licenses.mit;
              mainProgram = "machine";
              platforms = systems;
            };
          };
        default = machine;
      });

      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = lib.getExe self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        };
      });
    };
}
