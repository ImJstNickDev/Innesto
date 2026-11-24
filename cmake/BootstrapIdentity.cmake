file(SHA256 "${library}" digest)
get_filename_component(directory "${library}" DIRECTORY)
file(CONFIGURE OUTPUT "${directory}/innesto-bootstrap.sha256" CONTENT "@digest@\n" @ONLY)
