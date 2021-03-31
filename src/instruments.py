import cmd


class Shell(cmd.Cmd):
    intro = 'Type help or ? to list commands.'
    _instruments = {'leak', 'nfc', 'rs485'}
    _instrument = None
    _base_prompt = 'inst'
    use_rawinput = 0
    file = None

    @property
    def prompt(self) -> str:
        if not self._instrument:
            return f'({self._base_prompt}) '
        return f'({self._base_prompt}.{self._instrument}) '

    # ----- system commands -----
    def do_ci(self, instrument: str) -> None:
        """
        use a different instrument
        :param instrument: str (?i)
        """
        self._instrument = instrument.upper() if instrument in self._instruments else None

    def do_exit(self, arg):
        """
        clean up opened instruments, close them, and return to shell
        """
        return True


if __name__ == '__main__':
    Shell().cmdloop()
