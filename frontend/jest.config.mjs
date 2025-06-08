export default {
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/assets/js/tests'],
  testMatch: ['**/*.test.js'],
  moduleFileExtensions: ['js', 'mjs'],
  transform: {
    '^.+\\.[jt]sx?$': ['babel-jest', { configFile: './babel.config.cjs' }],
  },
};
