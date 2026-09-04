i18n = import('i18n')
gnome = import('gnome')

install_data('org.x.xepub.gschema.xml',
  install_dir: join_paths(get_option('datadir'), 'glib-2.0', 'schemas'))
install_data('xepub.svg',
  install_dir: join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps'))

i18n.merge_file(
  input: 'xepub.desktop.in', output: 'xepub.desktop', type: 'desktop',
  po_dir: join_paths(meson.project_source_root(), 'po'), install: true,
  install_dir: join_paths(get_option('datadir'), 'applications'))

gnome.post_install(glib_compile_schemas: true, gtk_update_icon_cache: true)
