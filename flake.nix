{
  description = "Synthetic and pinned public-domain corpus for thumtoo/biltoo pixel benchmarks";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f {
        inherit system;
        pkgs = import nixpkgs { inherit system; };
      });
    in {
      packages = forAllSystems ({ pkgs, system }: {
        default = self.packages.${system}.corpus;
        corpus = pkgs.stdenv.mkDerivation {
          pname = "pixel-bench-corpus";
          version = "0.1.0";
          src = ./.;
          nativeBuildInputs = [ pkgs.vips pkgs.python3 ];
          buildPhase = ''
            python3 generators/gen_synthetic.py --out "$PWD/out"
          '';
          installPhase = ''
            mkdir -p $out
            cp -a out/. $out/
            cp manifest/manifest.schema.json $out/manifest.schema.json
            if [ -f out/manifest.json ]; then
              cp out/manifest.json $out/manifest.json
            fi
          '';
          meta = with pkgs.lib; {
            description = "Benchmark image/archive fixtures for thumtoo pixel paths";
            license = licenses.gpl3Plus;
            platforms = platforms.unix;
          };
        };
      });

      apps = forAllSystems ({ pkgs, system }: {
        generate = {
          type = "app";
          program = "${pkgs.writeShellScript "pixel-bench-generate" ''
            set -euo pipefail
            out="''${1:-./out}"
            exec ${pkgs.python3}/bin/python3 ${./generators/gen_synthetic.py} --out "$out"
          ''}";
          meta.description = "Regenerate synthetic corpus into a directory";
        };
      });
    };
}
