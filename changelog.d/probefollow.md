## Fixed

- On 26.125 exports, post.log now warns, once per point, for each surface on the vorticity drag list whose CDp is exactly 0 (the solver declined it, as earlier builds print CDi 0), naming the surface and the build. This replaces the former warning that the rule was not applied; build 26.124 cannot discriminate.
