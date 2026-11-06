// The check that keeps mise.toml in its one structure (github.com/joeblew999/mise-check): each task one line that runs
// something, the flags and arguments it takes declared in its usage and passed by name, no POSIX shell syntax — so every
// task runs the same on macOS, Linux and Windows. `mise run root:check-mise` runs it.
package quote

import (
	"testing"

	misecheck "github.com/joeblew999/mise-check"
)

func TestRootMise(t *testing.T) { misecheck.Check(t, misecheck.Config{MiseFile: "mise.toml"}) }
