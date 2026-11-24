file(SHA256 "${image}" hash)
file(WRITE "${image}.sha256" "${hash}\n")
