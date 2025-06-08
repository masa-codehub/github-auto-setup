export default {
  testEnvironment: 'jsdom',
  roots: ['<rootDir>/assets/js/tests', '<rootDir>/tests'],
  testMatch: ['**/*.test.js'],
  moduleFileExtensions: ['js', 'mjs'],
  transform: {
    '^.+\\.[jt]sx?$': ['babel-jest', { configFile: './babel.config.cjs' }],
  },
};
