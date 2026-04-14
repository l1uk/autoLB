module autologbook/data-service

go 1.20

require (
	github.com/BurntSushi/toml v1.4.0
	github.com/fsnotify/fsnotify v1.8.0
	github.com/kardianos/service v1.2.4
	gopkg.in/natefinch/lumberjack.v2 v2.2.1
	modernc.org/sqlite v0.0.0-00010101000000-000000000000
)

require (
	github.com/dustin/go-humanize v1.0.1 // indirect
	github.com/google/go-cmp v0.5.8 // indirect
	github.com/google/uuid v1.6.0 // indirect
	github.com/kballard/go-shellquote v0.0.0-20180428030007-95032a82bc51 // indirect
	github.com/mattn/go-isatty v0.0.20 // indirect
	github.com/ncruces/go-strftime v0.1.9 // indirect
	github.com/remyoudompheng/bigfft v0.0.0-20230129092748-24d4a6f8daec // indirect
	golang.org/x/mod v0.16.0 // indirect
	golang.org/x/sys v0.34.0 // indirect
	golang.org/x/tools v0.19.0 // indirect
	lukechampine.com/uint128 v1.1.1 // indirect
	modernc.org/cc/v3 v3.38.1 // indirect
	modernc.org/ccgo/v3 v3.16.9 // indirect
	modernc.org/libc v1.55.3 // indirect
	modernc.org/mathutil v1.6.0 // indirect
	modernc.org/memory v1.8.0 // indirect
	modernc.org/opt v0.1.3 // indirect
	modernc.org/strutil v1.2.0 // indirect
	modernc.org/token v1.1.0 // indirect
)

replace (
	github.com/kardianos/service => github.com/kardianos/service v1.2.0
	golang.org/x/exp => golang.org/x/exp v0.0.0-20230522175609-2e198f4a06a1
	golang.org/x/sys => golang.org/x/sys v0.10.0
	modernc.org/sqlite => modernc.org/sqlite v1.19.1
)
