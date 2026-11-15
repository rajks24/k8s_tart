Pinned third-party CNI manifest downloaded on first new installation:
https://github.com/flannel-io/flannel/releases/download/<version>/kube-flannel.yml

The configured release and expected SHA-256 digest are in
`config/cluster.toml`. Every downloaded or cached copy is verified before it
can be applied. Review the upstream release and manifest, then update both
values deliberately when changing versions. The manifest is cached here for
review/reuse and is not embedded in the downloadable source archive.
